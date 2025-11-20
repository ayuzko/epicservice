# app/handlers/user/item_card.py

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.sqlite import Repositories
from app.services.items import format_item_card
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="item_card")

router = Router(name="user_item")


@router.message(Command("item"))
async def cmd_item(
    message: Message,
    repos: Repositories,
) -> None:
    """
    /item <артикул>

    Шукає товар у БД за артикулом і показує картку.
    Поки без кнопок, просто перевірка роботи БД та DI.
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Будь ласка, вкажіть артикул після команди.\n"
            "Наприклад:\n"
            "<code>/item 70117244</code>"
        )
        return

    sku = parts[1].strip()
    if not sku.isdigit() or len(sku) != 8:
        await message.answer(
            "Артикул має складатися з 8 цифр.\n"
            "Наприклад: <code>70117244</code>."
        )
        return

    log.info("Пошук товару за артикулом", extra={"sku": sku, "user_id": message.from_user.id})

    item = await repos.items.get_by_sku(sku)
    if not item:
        await message.answer(
            f"Товар з артикулом <code>{sku}</code> не знайдено в базі.\n"
            "Можливо, потрібно оновити імпорт."
        )
        return

    card_text = format_item_card(item)
    await message.answer(card_text)
