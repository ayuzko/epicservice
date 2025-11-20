# app/db/migrations.py

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Tuple

import aiosqlite

from app.config.settings import Settings
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="migrations")


SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def _parse_sqlite_path(db_url: str) -> Path:
    """
    Перетворює рядок на кшталт 'sqlite:///data/bot.db'
    або 'sqlite://data/bot.db' у локальний шлях до файлу.
    """
    if not db_url.startswith("sqlite"):
        raise ValueError(f"Неправильний sqlite URL: {db_url!r}")

    # Вирізаємо префікс 'sqlite://' або 'sqlite:///'
    if ":///" in db_url:
        path_part = db_url.split(":///")[1]
    else:
        path_part = db_url.split("://")[1]

    db_path = Path(path_part).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


async def run_sqlite_migrations(settings: Settings) -> None:
    """
    Запускає міграції для SQLite:
    - створює файл БД, якщо його ще немає;
    - виконує schema.sql (CREATE TABLE IF NOT EXISTS ...).

    Викликається тільки якщо DB_ENGINE == 'sqlite'.
    """
    db_path = _parse_sqlite_path(settings.DB_URL)
    log.info(f"Запуск міграцій SQLite для БД: {db_path}")

    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Файл схеми не знайдено: {SCHEMA_FILE}")

    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")

    async with aiosqlite.connect(db_path) as conn:
        # Включаємо зовнішні ключі на рівні з'єднання
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.executescript(schema_sql)
        await conn.commit()

    log.info("Міграції SQLite виконані успішно")


async def run_migrations(settings: Settings) -> None:
    """
    Точка входу для запуску міграцій.

    Зараз підтримує тільки SQLite, але інтерфейс залишено універсальним,
    щоб додати PostgreSQL / MySQL у майбутньому.
    """
    engine = settings.DB_ENGINE.lower()
    if engine == "sqlite":
        await run_sqlite_migrations(settings)
    else:
        log.warning(
            "DB_ENGINE=%s поки не підтримується міграціями. "
            "Пропускаємо run_migrations().",
            settings.DB_ENGINE,
        )


if __name__ == "__main__":
    # Ручний запуск міграцій: python -m app.db.migrations
    from app.config.settings import Settings
    from app.utils.logging_setup import setup_logging

    setup_logging(console_level="INFO", file_level="DEBUG")
    s = Settings()

    asyncio.run(run_migrations(s))
