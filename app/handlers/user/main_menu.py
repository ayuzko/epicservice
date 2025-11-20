# app/handlers/user/main_menu.py

from __future__ import annotations

from typing import List, Dict, Any, Tuple

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config.settings import Settings
from app.db.sqlite import Repositories
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
# Допоміжні функції (клавіатури, форматування)
# -------------------------


def _build_departments_keyboard(departments: List[Dict[str, Any]]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()

    for dept in departments:
        code = dept["dept_code"]
        name = dept["dept_name"] or "Без назви"
        count = dept["items_count"]
        text = f"{code} — {name} ({count} поз.)"
        cb_data = f"newlist:dept:{code}"
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
        await message.answer(
            "❌ Не вдалося завантажити список відділів з бази даних.\n"
            "Перевірте імпорт і логи бота."
        )
        return

    if not departments:
        await message.answer(
            "Поки що в базі немає жодного відділу.\n"
            "Спочатку виконайте імпорт залишків (через /import)."
        )
        return

    kb = _build_departments_keyboard(departments)

    await message.answer(
        "🆕 Створення нового списку.\n\n"
        "Оберіть, будь ласка, відділ, для якого будете збирати МТ:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("newlist:dept:"))
async def handle_new_list_choose_dept(
    callback: CallbackQuery,
) -> None:
    if not callback.data:
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return

    _, _, dept_code = parts
    await callback.answer()

    dept_name = get_department_name(dept_code)
    if dept_name:
        header = f"🆕 Новий список для відділу <b>{dept_code}</b> — {dept_name}."
    else:
        header = f"🆕 Новий список для відділу <b>{dept_code}</b>."

    kb = _build_mode_keyboard(dept_code)

    await callback.message.edit_text(
        header
        + "\n\n"
        "Оберіть режим формування списку:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("newlist:mode:"))
async def handle_new_list_choose_mode(
    callback: CallbackQuery,
    settings: Settings,
) -> None:
    if not callback.data or not callback.from_user:
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return

    _, _, mode, dept_code = parts
    user_id = callback.from_user.id

    await callback.answer()

    dept_name = get_department_name(dept_code)
    if dept_name:
        dept_part = f"<b>{dept_code}</b> — {dept_name}"
    else:
        dept_part = f"<b>{dept_code}</b>"

    mode_text, _ = _format_mode(mode)
    if mode == "manual":
        description = (
            "У цьому режимі ви самостійно додаєте позиції у список "
            "по артикулу або з підказок."
        )
    elif mode == "mt":
        description = (
            "У цьому режимі бот буде показувати товари з мертвим товаром (МТ) "
            "по черзі, а ви зможете додавати їх у список або пропускати."
        )
    else:
        description = "Сценарій ще не реалізований."

    try:
        list_id = await create_user_list(settings, user_id, dept_code, mode)
    except Exception:
        log.exception("Не вдалося створити запис списку в user_lists")
        await callback.message.edit_text(
            f"{mode_text}\n\n"
            f"Відділ: {dept_part}.\n\n"
            "❌ Сталася помилка при створенні списку в базі даних.\n"
            "Спробуйте пізніше або перевірте логи бота."
        )
        return

    await callback.message.edit_text(
        f"{mode_text}\n\n"
        f"Відділ: {dept_part}.\n"
        f"ID списку: <code>{list_id}</code>.\n\n"
        f"{description}\n\n"
        "Список збережено в базі даних у статусі 'draft'.\n"
        "Ви можете відкрити його через меню '📋 Мої списки' і додавати товари "
        "простим надсиланням артикулу (8 цифр)."
    )


# -------------------------
# "Мої списки" + відкриття списку
# -------------------------


@router.message(F.text == "📋 Мої списки")
async def handle_my_lists(
    message: Message,
    settings: Settings,
) -> None:
    if not message.from_user:
        await message.answer("Не вдалося визначити користувача.")
        return

    user_id = message.from_user.id
    log.info("Користувач відкрив 'Мої списки'", extra={"user_id": user_id})

    try:
        lists = await load_user_lists_for_user(settings, user_id, limit=10)
    except Exception:
        log.exception("Не вдалося завантажити списки користувача")
        await message.answer(
            "❌ Не вдалося завантажити ваші списки з бази даних.\n"
            "Спробуйте пізніше або перевірте логи бота."
        )
        return

    if not lists:
        await message.answer(
            "📋 У вас ще немає жодного списку.\n\n"
            "Натисніть '🆕 Новий список', щоб створити перший."
        )
        return

    lines = ["📋 Ваші останні списки:\n"]
    kb = InlineKeyboardBuilder()

    for lst in lists:
        mode_text, _ = _format_mode(lst["mode"])
        status_text = _format_status(lst["status"])
        dept_name = lst["dept_name"]
        if dept_name:
            dept_part = f"{lst['dept_code']} — {dept_name}"
        else:
            dept_part = lst["dept_code"]

        created = lst["created_at"]
        lines.append(
            f"• ID <code>{lst['id']}</code> | {mode_text} | статус: {status_text}\n"
            f"  Відділ: {dept_part}\n"
            f"  Створено: {created}"
        )

        kb.button(
            text=f"Відкрити список ID {lst['id']}",
            callback_data=f"lists:open:{lst['id']}",
        )

    kb.adjust(1)

    await message.answer("\n\n".join(lines), reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("lists:open:"))
async def handle_open_list(
    callback: CallbackQuery,
    settings: Settings,
) -> None:
    if not callback.data or not callback.from_user:
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return

    _, _, raw_id = parts
    try:
        list_id = int(raw_id)
    except ValueError:
        await callback.answer()
        return

    user_id = callback.from_user.id

    try:
        lst = await set_active_list(settings, user_id, list_id)
    except Exception:
        log.exception("Не вдалося активувати список")
        await callback.message.answer(
            "❌ Не вдалося відкрити список.\n"
            "Спробуйте пізніше або перевірте логи бота."
        )
        await callback.answer()
        return

    if lst is None:
        await callback.message.answer(
            "❌ Цей список вам не належить або не існує."
        )
        await callback.answer()
        return

    await callback.answer()

    mode_text, _ = _format_mode(lst["mode"])
    dept_name = lst["dept_name"]
    if dept_name:
        dept_part = f"{lst['dept_code']} — {dept_name}"
    else:
        dept_part = lst["dept_code"]

    await callback.message.answer(
        f"📋 Активний список ID <code>{lst['id']}</code>\n"
        f"Режим: {mode_text}\n"
        f"Відділ: {dept_part}\n\n"
        "Надішліть артикул (8 цифр), щоб додати товар у цей список.\n"
        "Якщо артикул знайдено в базі, бот покаже картку товару "
        "та підтвердить додавання."
    )


# -------------------------
# Додавання товару по артикулу
# -------------------------


@router.message(F.text.regexp(r"^\d{8}$"))
async def handle_add_item_to_active_list(
    message: Message,
    settings: Settings,
    repos: Repositories,
) -> None:
    if not message.from_user:
        await message.answer("Не вдалося визначити користувача.")
        return

    user_id = message.from_user.id
    sku = (message.text or "").strip()

    # Знаходимо активний список
    try:
        active_list = await get_active_list_for_user(settings, user_id)
    except Exception:
        log.exception("Не вдалося отримати активний список користувача")
        await message.answer(
            "❌ Не вдалося визначити активний список.\n"
            "Відкрийте його через '📋 Мої списки' і спробуйте ще раз."
        )
        return

    if not active_list:
        await message.answer(
            "У вас немає активного списку.\n\n"
            "Відкрийте потрібний список через '📋 Мої списки', "
            "натиснувши кнопку 'Відкрити список', а потім надішліть артикул."
        )
        return

    # Шукаємо товар у БД
    item = await repos.items.get_by_sku(sku)
    if not item:
        await message.answer(
            f"❌ Товар з артикулом <code>{sku}</code> не знайдено в базі.\n"
            "Перевірте артикул або оновіть імпорт."
        )
        return

    # Витягуємо id, sku, name з запису
    if isinstance(item, dict):
        item_id = int(item["id"])
        item_sku = str(item.get("sku") or sku)
        item_name = str(item.get("name") or "")
    else:
        item_id = int(getattr(item, "id"))
        item_sku = str(getattr(item, "sku", sku))
        item_name = str(getattr(item, "name", ""))

    # Додаємо рядок у list_items (list_id, item_id, sku, [sku_snapshot], [name_snapshot])
    try:
        await add_item_to_list(settings, active_list["id"], item_id, item_sku, item_name)
    except Exception:
        log.exception("Не вдалося додати товар у list_items")
        await message.answer(
            "❌ Сталася помилка при додаванні товару в список.\n"
            "Спробуйте ще раз або перевірте логи бота."
        )
        return

    card_text = format_item_card(item)

    await message.answer(
        card_text
        + "\n\n"
        f"✅ Товар додано до списку ID <code>{active_list['id']}</code>."
    )


# -------------------------
# Плейсхолдер "Стан складу"
# -------------------------


@router.message(F.text == "📦 Стан складу")
async def handle_stock_state(
    message: Message,
) -> None:
    user_id = message.from_user.id if message.from_user else None
    log.info("Користувач відкрив 'Стан складу'", extra={"user_id": user_id})

    await message.answer(
        "📦 Стан складу.\n\n"
        "Зараз функціонал у розробці.\n"
        "Тут можна буде подивитися загальний стан складу по відділу "
        "та фільтру МТ (2/3/5/6+ місяців без руху)."
    )
