# app/main.py

import asyncio
from typing import Set

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.config.settings import Settings
from app.db.migrations import run_migrations
from app.db.sqlite import create_sqlite_repositories, SqliteDatabase, Repositories
from app.handlers import register_all_handlers
from app.keyboards.main_menu import main_menu_kb
from app.utils.logging_setup import setup_logging, get_logger


log = get_logger(__name__, action="startup")


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


async def on_startup(bot: Bot, settings: Settings, db: SqliteDatabase, repos: Repositories) -> None:
    """
    Викликається при старті Dispatcher.

    Тут БД і репозиторії вже ініціалізовані та передані як залежності.
    """
    log.info("on_startup: бот успішно запущено")
    me = await bot.get_me()
    log.info(f"Бот: @{me.username} (id={me.id})")
    log.info("БД та репозиторії готові до роботи")


async def on_shutdown(bot: Bot, db: SqliteDatabase) -> None:
    """
    Викликається при зупинці Dispatcher.

    Закриваємо ресурси: БД, HTTP‑сесію бота тощо.
    """
    log.info("on_shutdown: бот зупиняється")
    await db.close()
    log.info("З'єднання з БД закрито")
    await bot.session.close()
    log.info("HTTP-сесія бота закрита")


def register_basic_handlers(dp: Dispatcher, settings: Settings) -> None:
    """
    Базові хендлери + підключення всіх роутерів.
    Тут же вішаємо головне меню на /start.
    """
    admin_ids = _parse_admin_ids(settings)

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        is_admin = user_id in admin_ids if user_id is not None else False

        kb = main_menu_kb(is_admin=is_admin)

        await message.answer(
            "Привіт! 👋\n\n"
            "Бот для роботи з мертвим товаром (МТ) запущений.\n"
            "Адміністратори можуть надіслати Excel/ODS‑файл для імпорту за допомогою /import,\n"
            "а користувачі можуть обрати дію через меню нижче.",
            reply_markup=kb,
        )

    # Підключаємо всі роутери (user + admin)
    register_all_handlers(dp)


async def main() -> None:
    # 1. Налаштовуємо логування (консоль + файл з ротацією)
    setup_logging(console_level="INFO", file_level="DEBUG")
    log.info("Старт програми")

    # 2. Читаємо налаштування з .env
    settings = Settings()
    log.info(f"DB_ENGINE={settings.DB_ENGINE}, DB_URL={settings.DB_URL}")

    # 3. Запускаємо міграції БД (поки що тільки SQLite)
    await run_migrations(settings)
    log.info("Міграції БД виконано")

    # 4. Створюємо підключення до БД та репозиторії (SQLite)
    if settings.DB_ENGINE.lower() != "sqlite":
        raise RuntimeError("Наразі підтримується лише DB_ENGINE=sqlite")

    db, repos = await create_sqlite_repositories(settings)
    log.info("БД та репозиторії ініціалізовано")

    # 5. Створюємо Bot і Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # 6. Кладемо об'єкти в контекст Dispatcher,
    #    щоб мати до них доступ у хендлерах та подіях життєвого циклу
    dp["settings"] = settings
    dp["db"] = db
    dp["repos"] = repos

    # 7. Реєструємо /start і всі роутери користувача/адміна
    register_basic_handlers(dp, settings)

    # 8. Реєструємо події життєвого циклу з DI (settings, db, repos будуть підкинуті автоматично)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    log.info("Починаємо polling...")
    try:
        await dp.start_polling(
            bot,
            settings=settings,
            db=db,
            repos=repos,
        )
    finally:
        log.info("Dispatcher зупинено")


if __name__ == "__main__":
    asyncio.run(main())
