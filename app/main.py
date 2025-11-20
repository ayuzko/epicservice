# app/main.py

import asyncio
import sys
from typing import Set

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.config.settings import Settings
from app.db.migrations import run_migrations
from app.db.session import AsyncSessionLocal
from app.handlers import register_all_handlers
from app.keyboards.main_menu import main_menu_kb
from app.utils.logging_setup import setup_logging, get_logger

# Для коректної роботи на Windows (фікс RuntimeError: Event loop is closed)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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


async def on_startup(bot: Bot) -> None:
    """
    Викликається при старті Dispatcher.
    """
    log.info("on_startup: бот успішно запущено")
    me = await bot.get_me()
    log.info(f"Бот: @{me.username} (id={me.id})")
    log.info("БД та репозиторії готові до роботи")


async def on_shutdown(bot: Bot) -> None:
    """
    Викликається при зупинці Dispatcher.
    """
    log.info("on_shutdown: бот зупиняється")
    await bot.session.close()
    log.info("HTTP-сесія бота закрита")


def register_basic_handlers(dp: Dispatcher, settings: Settings) -> None:
    """
    Базові хендлери + підключення всіх роутерів.
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
    # 1. Налаштовуємо логування
    setup_logging(console_level="INFO", file_level="DEBUG")
    log.info("Старт програми")

    # 2. Читаємо налаштування
    settings = Settings()
    log.info(f"DB_ENGINE={settings.DB_ENGINE}, DB_URL={settings.DB_URL}")

    # 3. Запускаємо міграції БД
    await run_migrations(settings)
    log.info("Міграції БД виконано")

    # 4. Створюємо Bot і Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # 5. Кладемо об'єкти в контекст Dispatcher
    dp["settings"] = settings
    # Замість db/repos тепер використовуємо прямі імпорти або DI через мідлварі,
    # але оскільки ми перейшли на session.py, передавати repos не обов'язково,
    # проте старі хендлери можуть очікувати налаштування.
    
    # 6. Реєструємо /start і всі роутери
    register_basic_handlers(dp, settings)

    # 7. Реєструємо події життєвого циклу
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    log.info("Починаємо polling...")
    try:
        await dp.start_polling(
            bot,
            settings=settings,
            # db=db,    <- Ці аргументи більше не потрібні, якщо ми перейшли на SQLAlchemy,
            # repos=repos  але якщо ви використовуєте їх у старих хендлерах через DI,
            #              то треба дивитися, чи не впаде код. 
            #              В нашому новому коді ми використовуємо AsyncSessionLocal напряму.
            #              Тому тут можна залишити settings, бо він використовується.
        )
    except Exception as e:
        log.error(f"Polling зупинено через помилку (або переривання мережі): {e}")
    finally:
        log.info("Dispatcher зупинено (finally)")
        # Додаткова гарантія закриття сесії
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # Ловимо Ctrl+C, щоб не показувати страшний Traceback
        print("\n🛑 Бот зупинений користувачем (Ctrl+C). Гарного дня!")