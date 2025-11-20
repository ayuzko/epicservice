# app/handlers/admin/import_excel.py

from __future__ import annotations

from pathlib import Path

from aiogram import F, Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, Document

from app.config.settings import Settings
from app.db.sqlite import Repositories
from app.services.importer import import_items_from_file
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="admin_import")

router = Router(name="admin_import")


# -------------------------
# Допоміжні функції
# -------------------------


def _ensure_import_dir() -> Path:
    """
    Гарантує існування директорії data/imports/ і повертає її шлях.
    """
    base = Path("data") / "imports"
    base.mkdir(parents=True, exist_ok=True)
    return base


async def _save_document_to_disk(document: Document, bot: Bot) -> Path:
    """
    Завантажує документ з Telegram у локальний файл у data/imports/.

    Aiogram 3: у Document немає .download, треба використовувати bot.download(...).
    Ім'я файлу: <file_unique_id>__<original_filename>
    """
    imports_dir = _ensure_import_dir()

    original_name = document.file_name or "import.xlsx"
    safe_name = original_name.replace("/", "_").replace("\\", "_")
    target = imports_dir / f"{document.file_unique_id}__{safe_name}"

    log.info("Збереження файлу імпорту", extra={"file": str(target)})
    await bot.download(document, destination=str(target))

    return target


def _parse_admin_ids(settings: Settings) -> set[int]:
    """
    Розбирає TELEGRAM_ADMIN_IDS із Settings (рядок) у множину int ID.
    Формат у .env: TELEGRAM_ADMIN_IDS=1962821395,123456789
    """
    raw = settings.TELEGRAM_ADMIN_IDS or ""
    ids: set[int] = set()
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

    Використовує TELEGRAM_ADMIN_IDS як рядок із .env,
    який парсимо у список чисел.
    """
    if not message.from_user:
        return False
    admin_ids = _parse_admin_ids(settings)
    return message.from_user.id in admin_ids


# -------------------------
# Хендлери
# -------------------------


@router.message(Command("import"))
async def cmd_import_help(
    message: Message,
    settings: Settings,
) -> None:
    """
    /import — коротка інструкція.

    Просто пояснює, що потрібно надіслати Excel/ODS-файл.
    """
    if not _is_admin(message, settings):
        await message.answer("Ця команда доступна лише адміністраторам.")
        return

    await message.answer(
        "Імпорт даних з файлу.\n\n"
        "Надішліть мені файл Excel або ODS з вигрузкою залишків, "
        "і я спробую імпортувати товари у базу.\n\n"
        "Порада: надсилайте файл Як документ, а не як фото."
    )


@router.message(F.document)
async def handle_import_document(
    message: Message,
    repos: Repositories,
    settings: Settings,
    bot: Bot,
) -> None:
    """
    Обробляє документ (Excel/ODS), надісланий адміном.

    Алгоритм:
    - перевіряємо, що відправник — адмін;
    - зберігаємо файл у data/imports/;
    - запускаємо import_items_from_file(..., repos.items);
    - показуємо короткий звіт.
    """
    if not _is_admin(message, settings):
        # Ігноруємо документи не-адмінів (щоб не заважати звичайним користувачам).
        return

    if not message.document:
        await message.answer("Не можу знайти документ у цьому повідомленні.")
        return

    document = message.document
    log.info(
        "Отримано файл для імпорту",
        extra={
            "user_id": message.from_user.id if message.from_user else None,
            "file_name": document.file_name,
            "mime_type": document.mime_type,
            "file_id": document.file_id,
        },
    )

    try:
        # 1. Зберігаємо файл на диск
        file_path = await _save_document_to_disk(document, bot)

        # 2. Запускаємо імпорт у БД
        await message.answer(f"Починаю імпорт з файлу:\n<code>{file_path.name}</code>")

        result = await import_items_from_file(
            file_path=file_path,
            items_repo=repos.items,
            deactivate_missing=True,
        )

        # 3. Відправляємо короткий звіт
        text = (
            "✅ Імпорт завершено.\n\n"
            f"Рядків у файлі: <b>{result.rows_total}</b>\n"
            f"Рядків оброблено (з артикулом): <b>{result.items_processed}</b>\n"
            f"Додано: <b>{result.added}</b>\n"
            f"Оновлено: <b>{result.updated}</b>\n"
            f"Відключено (відсутні у файлі): <b>{result.deactivated}</b>\n"
        )
        await message.answer(text)

    except Exception:
        log.exception("Помилка під час імпорту файлу")
        await message.answer(
            "❌ Сталася помилка під час імпорту файлу.\n"
            "Перевірте формат таблиці й логи бота."
        )
