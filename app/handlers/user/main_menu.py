# app/handlers/user/main_menu.py

from __future__ import annotations

from typing import List, Dict, Any, Tuple

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from app.config.settings import Settings
from app.db.session import AsyncSessionLocal
from app.db.models import Item, UserList
from app.services.items import format_item_card
from app.services.lists_service import (
    load_departments,
    create_user_list,
    load_user_lists_for_user,
    set_active_list,
    get_active_list_for_user,
    add_item_to_list,
)
from app.config.departments_map import get_department_name
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="user_main_menu")

router = Router(name="user_main_menu")


# -------------------------
# Допоміжні функції
# -------------------------


def _build_departments_keyboard(departments: List[Dict[str, Any]], prefix: str = "newlist:dept") -> InlineKeyboardBuilder:
    """Будує клавіатуру відділів з динамічним префіксом callback_data."""
    kb = InlineKeyboardBuilder()

    for dept in departments:
        code = dept["dept_code"]
        name = dept["dept_name"] or "Без назви"
        count = dept["items_count"]
        text = f"{code} — {name} ({count} поз.)"
        cb_data = f"{prefix}:{code}"
        kb.button(text=text[:64], callback_data=cb_data)

    kb.adjust(1)
    return kb


def _build_mode_keyboard(dept_code: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📝 Ручний режим",
        callback_data=f"newlist:mode:manual:{dept_code}",
    )
    kb.button(
        text="♻️ Карусель МТ",
        callback_data=f"newlist:mode:mt:{dept_code}",
    )
    kb.adjust(1)
    return kb


def _format_mode(mode: str) -> Tuple[str, str]:
    if mode == "manual":
        return "📝 Ручний", "manual"
    if mode == "mt":
        return "♻️ Карусель МТ", "mt"
    return "❓ Невідомий", mode


def _format_status(status: str) -> str:
    status = (status or "").lower()
    if status == "draft":
        return "чернетка"
    if status == "active":
        return "активний"
    if status == "closed":
        return "закритий"
    return status or "невідомий"


async def _get_item_by_sku(sku: str) -> Item | None:
    """Допоміжна функція для пошуку товару (SQLAlchemy)."""
    async with AsyncSessionLocal() as session:
        stmt = select(Item).where(Item.sku == sku)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


# -------------------------
# Хендлери "Новий список"
# -------------------------


@router.message(F.text == "🆕 Новий список")
async def handle_new_list(
    message: Message,
    settings: Settings,
) -> None:
    user_id = message.from_user.id if message.from_user else None
    log.info("Користувач натиснув 'Новий список'", extra={"user_id": user_id})

    try:
        departments = await load_departments(settings)
    except Exception:
        log.exception("Не вдалося завантажити відділі з БД")
        await message.answer("❌ Помилка завантаження відділів.")
        return

    if not departments:
        await message.answer(
            "Поки що в базі немає жодного відділу.\n"
            "Спочатку виконайте імпорт залишків (через /import)."
        )
        return

    kb = _build_departments_keyboard(departments, prefix="newlist:dept")

    await message.answer(
        "🆕 Створення нового списку.\n\n"
        "Оберіть, будь ласка, відділ:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("newlist:dept:"))
async def handle_new_list_choose_dept(
    callback: CallbackQuery,
) -> None:
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        return

    _, _, dept_code = parts
    await callback.answer()

    dept_name = get_department_name(dept_code)
    dept_part = f"<b>{dept_code}</b>"
    if dept_name:
        dept_part += f" — {dept_name}"

    kb = _build_mode_keyboard(dept_code)

    await callback.message.edit_text(
        f"🆕 Новий список для відділу {dept_part}.\n\n"
        "Оберіть режим формування списку:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("newlist:mode:"))
async def handle_new_list_choose_mode(
    callback: CallbackQuery,
    settings: Settings,
) -> None:
    parts = callback.data.split(":")
    # newlist:mode:manual:10
    if len(parts) != 4:
        return

    _, _, mode, dept_code = parts
    user_id = callback.from_user.id

    await callback.answer()

    dept_name = get_department_name(dept_code)
    dept_part = f"<b>{dept_code}</b>" + (f" — {dept_name}" if dept_name else "")
    mode_text, _ = _format_mode(mode)

    if mode == "manual":
        desc = "У цьому режимі ви самостійно додаєте позиції по артикулу."
    elif mode == "mt":
        desc = "У цьому режимі бот буде пропонувати товари без руху (МТ)."
    else:
        desc = ""

    try:
        list_id = await create_user_list(settings, user_id, dept_code, mode)
    except Exception:
        log.exception("Помилка створення списку")
        await callback.message.edit_text("❌ Помилка створення списку.")
        return

    await callback.message.edit_text(
        f"{mode_text}\n\n"
        f"Відділ: {dept_part}.\n"
        f"ID списку: <code>{list_id}</code>.\n\n"
        f"{desc}\n\n"
        "Список збережено як 'чернетку'. Ви можете знайти його в меню '📋 Мої списки' та відкрити для роботи."
    )


# -------------------------
# "Мої списки" + відкриття списку
# -------------------------


@router.message(F.text == "📋 Мої списки")
async def handle_my_lists(
    message: Message,
    settings: Settings,
) -> None:
    user_id = message.from_user.id
    
    try:
        lists = await load_user_lists_for_user(settings, user_id, limit=10)
    except Exception:
        log.exception("Помилка завантаження списків")
        await message.answer("❌ Помилка завантаження списків.")
        return

    if not lists:
        await message.answer(
            "📋 У вас ще немає списків.\n"
            "Натисніть '🆕 Новий список', щоб створити."
        )
        return

    lines = ["📋 <b>Ваші останні списки:</b>\n"]
    kb = InlineKeyboardBuilder()

    for lst in lists:
        mode_text, _ = _format_mode(lst["mode"])
        status_text = _format_status(lst["status"])
        dept_name = lst["dept_name"]
        dept_part = f"{lst['dept_code']}" + (f" — {dept_name}" if dept_name else "")

        lines.append(
            f"• ID <code>{lst['id']}</code> | {mode_text} | {status_text}\n"
            f"  Відділ: {dept_part}\n"
            f"  {lst['created_at']}"
        )
        kb.button(
            text=f"Відкрити ID {lst['id']}",
            callback_data=f"lists:open:{lst['id']}",
        )

    kb.adjust(1)
    await message.answer("\n\n".join(lines), reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("lists:open:"))
async def handle_open_list(
    callback: CallbackQuery,
    settings: Settings,
) -> None:
    try:
        list_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        return

    user_id = callback.from_user.id
    
    # Активуємо список
    lst = await set_active_list(settings, user_id, list_id)
    
    if not lst:
        await callback.answer("Список не знайдено або він чужий.", show_alert=True)
        return

    await callback.answer()

    mode_text, _ = _format_mode(lst["mode"])
    dept_name = lst["dept_name"]
    dept_part = f"{lst['dept_code']}" + (f" — {dept_name}" if dept_name else "")

    await callback.message.answer(
        f"✅ <b>Список активовано!</b>\n\n"
        f"ID: <code>{lst['id']}</code>\n"
        f"Відділ: {dept_part}\n"
        f"Режим: {mode_text}\n\n"
        "Тепер ви можете надсилати артикули (8 цифр) або скористатися каруселлю (якщо обрано МТ)."
    )


# -------------------------
# "Стан складу" (Stock State Funnel)
# -------------------------


@router.message(F.text == "📦 Стан складу")
async def handle_stock_state(
    message: Message,
    settings: Settings,
) -> None:
    """
    Крок 1: Вибір відділу для аналізу.
    """
    user_id = message.from_user.id
    log.info("Користувач відкрив 'Стан складу'", extra={"user_id": user_id})

    try:
        departments = await load_departments(settings)
    except Exception:
        log.exception("Помилка")
        await message.answer("❌ Помилка бази даних.")
        return
    
    if not departments:
        await message.answer("База порожня.")
        return

    # Використовуємо префікс stock:dept
    kb = _build_departments_keyboard(departments, prefix="stock:dept")
    await message.answer(
        "📦 <b>Стан складу</b>\n\n"
        "Оберіть відділ для аналізу:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("stock:dept:"))
async def handle_stock_dept_stats(
    callback: CallbackQuery,
) -> None:
    """
    Крок 2: Інформація про відділ і вибір фільтра місяців.
    """
    dept_code = callback.data.split(":")[2]
    
    # Отримуємо загальну кількість та ім'я відділу (можна оптимізувати кешем, 
    # але зробимо чесний запит для актуальності)
    async with AsyncSessionLocal() as session:
        # Загальна кількість
        count_stmt = select(func.count(Item.id)).where(Item.dept_code == dept_code)
        total_items = (await session.execute(count_stmt)).scalar() or 0
        
        # Назва відділу (беремо з будь-якого товару цього відділу)
        name_stmt = select(Item.dept_name).where(Item.dept_code == dept_code).limit(1)
        db_name = (await session.execute(name_stmt)).scalar()
    
    dept_name = get_department_name(dept_code) or db_name or "Невідомий"
    
    kb = InlineKeyboardBuilder()
    # Кнопки фільтрів
    for m in [2, 3, 4, 5, 6]:
        label = f"{m} міс." if m < 6 else "6+ міс."
        kb.button(text=label, callback_data=f"stock:filter:{dept_code}:{m}")
    
    kb.button(text="🔙 Назад", callback_data="stock:back_to_depts") # Можна реалізувати повернення
    kb.adjust(3)

    await callback.message.edit_text(
        f"📊 Відділ: <b>{dept_code} — {dept_name}</b>\n"
        f"Всього артикулів: <b>{total_items}</b>\n\n"
        "Оберіть період без руху (МТ), щоб відфільтрувати товари:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("stock:filter:"))
async def handle_stock_filter(
    callback: CallbackQuery,
) -> None:
    """
    Крок 3: Результат фільтрації і пропозиція запустити карусель.
    """
    # stock:filter:CODE:MONTHS
    parts = callback.data.split(":")
    dept_code = parts[2]
    months = float(parts[3])
    
    async with AsyncSessionLocal() as session:
        # Рахуємо кількість МТ
        stmt = select(func.count(Item.id)).where(
            Item.dept_code == dept_code,
            Item.mt_months >= months
        )
        mt_count = (await session.execute(stmt)).scalar() or 0
        
    kb = InlineKeyboardBuilder()
    if mt_count > 0:
        # Кнопка запуску каруселі
        # Передаємо dept_code і months в callback
        kb.button(
            text="🚀 Почати збір (Карусель)", 
            callback_data=f"car:start:{dept_code}:{months}"
        )
    
    kb.button(text="🔙 Інший фільтр", callback_data=f"stock:dept:{dept_code}")
    kb.adjust(1)
    
    label = f"{int(months)} і більше" if months < 6 else "6 і більше"
    
    await callback.message.edit_text(
        f"🔎 Фільтр: <b>{label} місяців</b>\n"
        f"Знайдено МТ артикулів: <b>{mt_count}</b>\n\n"
        "Бажаєте почати збір цих товарів?",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data == "stock:back_to_depts")
async def handle_back_to_depts(message: Message, settings: Settings):
    # Просто викликаємо хендлер першого кроку, але це callback, тому треба трюк
    # Простіше просто надіслати нове повідомлення або відредагувати
    # Тут для простоти:
    pass 


# -------------------------
# Додавання товару по артикулу (Text Handler)
# -------------------------


@router.message(F.text.regexp(r"^\d{8}$"))
async def handle_add_item_to_active_list(
    message: Message,
    settings: Settings,
) -> None:
    user_id = message.from_user.id
    sku = (message.text or "").strip()

    # 1. Активний список
    try:
        active_list = await get_active_list_for_user(settings, user_id)
    except Exception:
        log.exception("Помилка отримання активного списку")
        return

    if not active_list:
        await message.answer(
            "У вас немає активного списку.\n"
            "Відкрийте '📋 Мої списки' або створіть новий."
        )
        return
    
    # Перевірка на відповідність відділу (Правило: один список - один відділ)
    # Якщо ми хочемо сувору перевірку, треба дістати відділ товару ДО додавання.
    
    # 2. Шукаємо товар
    item = await _get_item_by_sku(sku)
    if not item:
        await message.answer(f"❌ Товар {sku} не знайдено.")
        return

    # Перевірка відділу
    # active_list["dept_code"] vs item.dept_code
    if str(item.dept_code) != str(active_list["dept_code"]):
        await message.answer(
            f"⚠️ <b>Увага!</b> Цей товар з відділу {item.dept_code}, "
            f"а ваш список для відділу {active_list['dept_code']}.\n"
            "Додавання заборонено правилами."
        )
        return

    # 3. Додаємо в список
    # Конвертуємо SQLAlchemy об'єкт у dict для сервісу
    item_dict = {
        "sku": item.sku,
        "name": item.name,
        "dept_code": item.dept_code,
        "price": item.price,
        "mt_months": item.mt_months
    }
    
    try:
        await add_item_to_list(settings, active_list["id"], item.id, item_dict)
    except Exception:
        log.exception("Помилка додавання")
        await message.answer("❌ Помилка при додаванні.")
        return

    # 4. Показуємо картку (в item_card.py логіка показу картки, тут дублюємо або викликаємо)
    # Найпростіше - надіслати картку як response.
    # Але краще, щоб це робив item_card handler. 
    # Однак ми тут вже обробили меседж. Тому формуємо відповідь тут.
    
    card_text = format_item_card(item_dict)
    
    await message.answer(
        card_text + f"\n\n✅ <b>Додано в список {active_list['id']}</b>"
    )