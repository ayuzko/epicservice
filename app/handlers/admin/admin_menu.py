# app/handlers/admin/admin_menu.py

from __future__ import annotations

from typing import Set

from aiogram import Router, F
from aiogram.types import Message

from app.config.settings import Settings
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="admin_menu")

router = Router(name="admin_menu")


def _parse_admin_ids(settings: Settings) -> Set[int]:
    """
    Розбирає TELEGRAM_ADMIN_IDS із Settings (рядок) у множину int ID.
    Формат у .env: TELEGRAM_ADMIN_IDS=1962821395,123456789
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
    Обробка кнопки "⚙️ Адмін‑панель" у головному меню.

    Поки що просте текстове адмін‑меню:
    - нагадує про /import;
    - далі сюди додамо інші адмінські дії (розсилки, модерація тощо).
    """
    if not _is_admin(message, settings):
        await message.answer("Ця кнопка доступна лише адміністраторам.")
        return

    user_id = message.from_user.id if message.from_user else None
    log.info("Адмін відкрив адмін‑панель", extra={"user_id": user_id})

    await message.answer(
        "⚙️ Адмін‑панель.\n\n"
        "Доступні дії:\n"
        "• Імпорт залишків з Excel/ODS — команда /import (надішліть файл як документ).\n"
        "• Надалі тут з'являться інші інструменти: перегляд логів імпорту, "
        "розсилки, модерація фото та інше."
    )
