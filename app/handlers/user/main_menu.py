# app/handlers/user/main_menu.py

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any

import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config.settings import Settings
from app.config.departments_map import get_department_name
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="user_main_menu")

router = Router(name="user_main_menu")


# -------------------------
# Допоміжні функції
# -------------------------


def _get_sqlite_path(settings: Settings) -> Path:
    """
    Дістає шлях до файлу SQLite з DB_URL виду 'sqlite:///data/bot.db'.
    """
    url = settings.DB_URL
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Наразі підтримується лише SQLite з DB_URL=sqlite:///...")
    path_str = url.replace("sqlite:///", "", 1)
    return Path(path_str).expanduser().resolve()


async def _load_departments(settings: Settings) -> List[Dict[str, Any]]:
    """
    Читає з БД унікальні відділи з таблиці items.

    Повертає список словників:
    [
        {"dept_code": "100", "dept_name": "Текстиль", "items_count": 123},
        ...
    ]

    Якщо dept_name порожнє – підставляємо назву з departments.json.
    """
    db_path = _get_sqlite_path(settings)
    log.info("Завантажуємо відділи з SQLite", extra={"db_path": str(db_path)})

    query = """
    SELECT
        dept_code,
        COALESCE(dept_name, '') AS dept_name,
        COUNT(*) AS items_count
    FROM items
    WHERE dept_code IS NOT NULL AND TRIM(dept_code) <> ''
    GROUP BY dept_code, dept_name
    ORDER BY dept_code
    """

    departments: List[Dict[str, Any]] = []

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query) as cur:
            rows = await cur.fetchall()

    for row in rows:
        code = str(row["dept_code"])
        db_name = str(row["dept_name"] or "").strip()
        mapped_name = get_department_name(code)

        final_name = db_name or mapped_name or ""
        departments.append(
            {
                "dept_code": code,
                "dept_name": final_name,
                "items_count": int(row["items_count"]),
            }
        )

    log.info(
        "Знайдено відділів: %s",
        len(departments),
        extra={"departments": [f'{d["dept_code"]}={d["dept_name"]}' for d in departments]},
    )
    return departments


def _build_departments_keyboard(departments: List[Dict[str, Any]]) -> InlineKeyboardBuilder:
    """
    Створює інлайн‑клавіатуру з переліком відділів.

    Кожна кнопка:
    - текст: "<код> — <назва> (N поз.)"
    - callback_data: "newlist:dept:<код>"
    """
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


# -------------------------
# Хендлери кнопок меню
# -------------------------


@router.message(F.text == "🆕 Новий список")
async def handle_new_list(
    message: Message,
    settings: Settings,
) -> None:
    """
    Обробка кнопки "🆕 Новий список".

    Етап 1: даємо користувачу вибрати відділ з інлайн‑клавіатури.
    """
    user_id = message.from_user.id if message.from_user else None
    log.info("Користувач натиснув 'Новий список'", extra={"user_id": user_id})

    try:
        departments = await _load_departments(settings)
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
    """
    Обробка вибору відділу з інлайн‑клавіатури "Новий список".

    Поки що це тільки підтвердження вибору.
    """
    if not callback.data:
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return

    _, _, dept_code = parts

    await callback.answer()

    # Назву відділу беремо з маппінгу departments.json
    dept_name = get_department_name(dept_code)

    if dept_name:
        header = f"🆕 Новий список для відділу <b>{dept_code}</b> — {dept_name}."
    else:
        header = f"🆕 Новий список для відділу <b>{dept_code}</b>."

    await callback.message.edit_text(
        header
        + "\n\n"
        "Далі тут з'явиться вибір режиму списку (ручний / карусель МТ) "
        "та кроки додавання товарів.\n"
        "Поки що це тільки вибір відділу."
    )


@router.message(F.text == "📋 Мої списки")
async def handle_my_lists(
    message: Message,
) -> None:
    """
    Обробка кнопки "📋 Мої списки".
    """
    user_id = message.from_user.id if message.from_user else None
    log.info("Користувач відкрив 'Мої списки'", extra={"user_id": user_id})

    await message.answer(
        "📋 Мої списки.\n\n"
        "Функціонал ще в розробці.\n"
        "Тут будуть показані ваші активні та збережені списки для збору товару."
    )


@router.message(F.text == "📦 Стан складу")
async def handle_stock_state(
    message: Message,
) -> None:
    """
    Обробка кнопки "📦 Стан складу".
    """
    user_id = message.from_user.id if message.from_user else None
    log.info("Користувач відкрив 'Стан складу'", extra={"user_id": user_id})

    await message.answer(
        "📦 Стан складу.\n\n"
        "Зараз функціонал у розробці.\n"
        "Тут можна буде подивитися загальний стан складу по відділу "
        "та фільтру МТ (2/3/5/6+ місяців без руху)."
    )
