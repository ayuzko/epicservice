# app/handlers/user/item_card.py

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config.settings import Settings
from app.db.sqlite import Repositories
from app.services.items import format_item_card
from app.services.lists_service import get_active_list_for_user, add_item_to_list
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="item_card")

router = Router(name="user_item")


@router.message(Command("item"))
async def cmd_item(
    message: Message,
    settings: Settings,
    repos: Repositories,
) -> None:
    """
    /item <артикул>
    Показує картку товару + кнопку додавання, якщо є активний список.
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("Вкажіть артикул: <code>/item 12345678</code>")
        return

    sku = parts[1].strip()
    
    # Валідація (спрощена)
    if not sku.isdigit() or len(sku) != 8:
        await message.answer("Артикул має бути 8 цифр.")
        return

    item = await repos.items.get_by_sku(sku)
    if not item:
        await message.answer(f"Товар {sku} не знайдено.")
        return

    card_text = format_item_card(item)

    # --- Будуємо кнопки ---
    kb = InlineKeyboardBuilder()
    user_id = message.from_user.id

    # Перевіряємо, чи є куди додавати
    active_list = await get_active_list_for_user(settings, user_id)
    
    if active_list:
        list_id = active_list["id"]
        kb.button(
            text=f"✅ Додати в список {list_id}", 
            callback_data=f"item:add:{sku}"
        )
    else:
        # Якщо списку немає, можна запропонувати створити/відкрити
        kb.button(text="📋 Мої списки", callback_data="menu:my_lists")

    kb.button(text="❌ Закрити", callback_data="item:close")
    kb.adjust(1)

    await message.answer(card_text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("item:add:"))
async def callback_add_item(
    callback: CallbackQuery,
    settings: Settings,
    repos: Repositories,
):
    sku = callback.data.split(":")[2]
    user_id = callback.from_user.id
    
    active_list = await get_active_list_for_user(settings, user_id)
    if not active_list:
        await callback.answer("Немає активного списку!", show_alert=True)
        return

    item = await repos.items.get_by_sku(sku)
    if not item:
        await callback.answer("Товар не знайдено в БД", show_alert=True)
        return

    # Додаємо
    await add_item_to_list(settings, active_list["id"], int(item["id"]), item)
    
    await callback.answer("Додано!", show_alert=False)
    await callback.message.edit_text(
        f"{callback.message.html_text}\n\n✅ <b>Додано в список {active_list['id']}</b>",
        reply_markup=None # Прибираємо кнопку додавання, щоб не дублювати
    )


@router.callback_query(F.data == "item:close")
async def callback_close(callback: CallbackQuery):
    await callback.message.delete()