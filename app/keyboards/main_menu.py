# app/keyboards/main_menu.py

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_kb(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Головне меню бота для звичайного користувача.

    Кнопки:
    - 🆕 Новий список
    - 📋 Мої списки
    - 📦 Стан складу
    - ⚙️ Адмін‑панель (тільки для адміна)
    """
    buttons_row_1 = [
        KeyboardButton(text="🆕 Новий список"),
        KeyboardButton(text="📋 Мої списки"),
    ]

    buttons_row_2 = [
        KeyboardButton(text="📦 Стан складу"),
    ]

    keyboard_rows = [buttons_row_1, buttons_row_2]

    if is_admin:
        keyboard_rows.append(
            [KeyboardButton(text="⚙️ Адмін‑панель")]
        )

    return ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть дію з меню…",
    )
