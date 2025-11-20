# app/handlers/user/item_card.py

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.config.settings import Settings
from app.db.session import AsyncSessionLocal
from app.db.models import Item, ListItem
from app.services.items import format_item_card
from app.services.lists_service import (
    get_active_list_for_user,
    add_item_to_list,
    update_item_qty
)
from app.keyboards.item_actions import build_item_action_kb
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="item_card")

router = Router(name="user_item")


async def _get_item_by_sku(sku: str) -> Item | None:
    """Допоміжна функція для пошуку товару."""
    async with AsyncSessionLocal() as session:
        stmt = select(Item).where(Item.sku == sku)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def _get_list_item_info(list_id: int, item_id: int) -> dict:
    """Отримує інформацію про кількість товару в конкретному списку."""
    async with AsyncSessionLocal() as session:
        stmt = select(ListItem).where(
            ListItem.list_id == list_id,
            ListItem.item_id == item_id
        )
        result = await session.execute(stmt)
        li = result.scalar_one_or_none()
        
        if li:
            return {
                "qty": li.qty,
                "surplus": li.surplus_qty
            }
        return {"qty": 0.0, "surplus": 0.0}


@router.message(Command("item"))
async def cmd_item(
    message: Message,
    settings: Settings,
) -> None:
    """
    /item <артикул>
    Показує картку товару та панель дій.
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("Вкажіть артикул: <code>/item 70117244</code>")
        return

    sku = parts[1].strip()
    
    if not sku.isdigit() or len(sku) != 8:
        await message.answer("Артикул має складатися з 8 цифр.")
        return

    # 1. Шукаємо товар
    item = await _get_item_by_sku(sku)
    if not item:
        await message.answer(f"❌ Товар з артикулом <code>{sku}</code> не знайдено.")
        return

    user_id = message.from_user.id
    card_text = format_item_card(item.__dict__) # format_item_card очікує dict

    # 2. Перевіряємо активний список
    active_list = await get_active_list_for_user(settings, user_id)
    
    if active_list:
        # Отримуємо поточний стан (скільки вже зібрано)
        li_info = await _get_list_item_info(active_list["id"], item.id)
        in_list_qty = li_info["qty"] + li_info["surplus"]
        
        # Доступно по базі
        available = max(0.0, item.base_qty - item.base_reserve)
        
        kb = build_item_action_kb(
            sku=item.sku,
            current_qty=0, # Тут можна було б зберігати проміжний ввід, але поки 0
            max_qty=available,
            in_list_qty=in_list_qty
        )
        await message.answer(card_text, reply_markup=kb)
    else:
        # Якщо списку немає, просто показуємо картку
        await message.answer(card_text)


@router.callback_query(F.data.startswith("act:"))
async def handle_item_action(
    callback: CallbackQuery, 
    settings: Settings
):
    """
    Обробка кнопок [+], [-], [Додати все] тощо.
    """
    parts = callback.data.split(":")
    action = parts[1]
    
    if action == "noop":
        await callback.answer()
        return
    
    if action == "back":
        await callback.message.delete()
        return

    # act:inc:SKU
    if len(parts) < 3:
        await callback.answer("Некоректні дані", show_alert=True)
        return

    sku = parts[2]
    user_id = callback.from_user.id
    
    # 1. Перевірки
    active_list = await get_active_list_for_user(settings, user_id)
    if not active_list:
        await callback.answer("Немає активного списку!", show_alert=True)
        return

    item = await _get_item_by_sku(sku)
    if not item:
        await callback.answer("Товар не знайдено", show_alert=True)
        return

    # 2. Додаємо товар у список (якщо його ще немає)
    # Це безпечно, бо add_item_to_list перевіряє наявність
    await add_item_to_list(settings, active_list["id"], item.id, item.__dict__)

    # 3. Визначаємо дельту
    delta = 0.0
    set_exact = None
    is_surplus = (action == "surplus")

    if action == "inc":
        delta = 1.0
    elif action == "dec":
        delta = -1.0
    elif action == "all":
        # "Додати все" = встановити кількість рівну доступному залишку
        available = max(0.0, item.base_qty - item.base_reserve)
        set_exact = available
    elif action == "input":
        # Тут має бути FSM для вводу числа, поки заглушка
        await callback.answer("Ввід числа поки в розробці", show_alert=True)
        return
    elif action == "photo":
         await callback.answer("Фото поки в розробці", show_alert=True)
         return
    elif action == "comment":
         await callback.answer("Коментарі поки в розробці", show_alert=True)
         return

    # 4. Оновлюємо кількість
    res = await update_item_qty(
        settings, active_list["id"], item.id,
        delta=delta, set_exact=set_exact, is_surplus=is_surplus
    )

    if res["status"] == "error":
        await callback.answer(res["msg"], show_alert=True)
        return

    # 5. Оновлюємо клавіатуру (безшовність)
    total_in_list = res["collected"] + res["surplus"]
    
    new_kb = build_item_action_kb(
        sku=sku,
        current_qty=0,
        max_qty=res["available"],
        in_list_qty=total_in_list
    )

    # Щоб не було помилки "message is not modified"
    try:
        await callback.message.edit_reply_markup(reply_markup=new_kb)
    except Exception:
        pass

    await callback.answer()