# app/handlers/admin/admin_menu.py

from __future__ import annotations

from typing import Set

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config.settings import Settings
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="admin_menu")

router = Router(name="admin_menu")


def _parse_admin_ids(settings: Settings) -> Set[int]:
    """
    Розбирає TELEGRAM_ADMIN_IDS із Settings (рядок) у множину int ID.
    """
    raw = settings.TELEGRAM_ADMIN_IDS or ""
    ids: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def _is_admin(message: Message, settings: Settings) -> bool:
    """
    Перевірка, чи є користувач адміном.
    """
    if not message.from_user:
        return False
    admin_ids = _parse_admin_ids(settings)
    return message.from_user.id in admin_ids


@router.message(F.text == "⚙️ Адмін‑панель")
async def handle_admin_panel(
    message: Message,
    settings: Settings,
) -> None:
    """
    Обробка кнопки "⚙️ Адмін‑панель".
    Тепер виводить Inline-кнопки дій.
    """
    if not _is_admin(message, settings):
        await message.answer("Ця кнопка доступна лише адміністраторам.")
        return

    user_id = message.from_user.id if message.from_user else None
    log.info("Адмін відкрив адмін‑панель", extra={"user_id": user_id})

    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Інструкція імпорту", callback_data="admin:import_help")
    kb.button(text="📊 Статистика (WIP)", callback_data="admin:stats")
    kb.button(text="❌ Закрити", callback_data="admin:close")
    kb.adjust(1)

    await message.answer(
        "⚙️ <b>Адмін‑панель</b>\n\n"
        "Оберіть дію:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data == "admin:import_help")
async def cb_import_help(callback: CallbackQuery):
    """
    Показує інструкцію по імпорту.
    """
    await callback.answer()
    await callback.message.answer(
        "<b>Інструкція імпорту</b>\n\n"
        "Щоб оновити залишки:\n"
        "1. Підготуйте файл .xlsx або .ods.\n"
        "2. Просто надішліть цей файл сюди в чат (як Документ).\n"
        "3. Бот автоматично розпізнає його та оновить базу.\n\n"
        "Або використайте команду /import, щоб отримати цю ж підказку."
    )


@router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery):
    """
    Заглушка для статистики.
    """
    await callback.answer("Функціонал у розробці 🛠", show_alert=True)


@router.callback_query(F.data == "admin:close")
async def cb_close(callback: CallbackQuery):
    """
    Закриває адмін-панель.
    """
    await callback.message.delete()