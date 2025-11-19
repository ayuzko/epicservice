import asyncio
import os
import sys
from loguru import logger

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

# Імпорт бази даних
from database.core import init_db
# Імпорт Middleware
from middlewares.db import DbSessionMiddleware
# Імпорт Хендлерів
from handlers import common, admin_panel, user_flow, list_flow

# Завантаження налаштувань
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

async def on_startup(bot: Bot):
    """Дії при старті бота"""
    logger.info("🏗 Перевірка Бази Даних...")
    await init_db()
    logger.info("✅ База даних готова.")

    # Сповіщення адмінів
    for admin_id in ADMIN_IDS:
        if admin_id:
            try:
                await bot.send_message(
                    chat_id=admin_id.strip(), 
                    text="🤖 <b>Бот успішно запущено!</b>\nСистема готова до роботи."
                )
            except Exception as e:
                logger.warning(f"Не вдалося відправити старт адміну {admin_id}: {e}")

async def main():
    # 1. Налаштування логів
    logger.remove()
    logger.add(sys.stderr, level=LOG_LEVEL)
    logger.add("logs/bot.log", rotation="10 MB", level="DEBUG", compression="zip")

    if not BOT_TOKEN:
        logger.error("❌ Помилка: BOT_TOKEN не знайдено в .env")
        return

    # 2. Ініціалізація
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 3. 🔌 ПІДКЛЮЧЕННЯ MIDDLEWARE
    dp.update.middleware(DbSessionMiddleware())

    # 4. 🔌 ПІДКЛЮЧЕННЯ РОУТЕРІВ (УВАГА НА ПОРЯДОК!)
    
    dp.include_router(common.router)       # /start, /help
    dp.include_router(admin_panel.router)  # Адмінка
    
    # 👇 ВАЖЛИВО: Списки мають бути ПЕРЕД пошуком
    dp.include_router(list_flow.router)    # Кнопки "Новий список", "Мій список"
    
    # 👇 Пошук йде останнім, бо він ловить "все інше"
    dp.include_router(user_flow.router)    

    # 5. Запуск
    dp.startup.register(on_startup)
    
    logger.info("🚀 Бот запускається...")
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот зупинено")