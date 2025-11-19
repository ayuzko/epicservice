import asyncio
import os
import sys
from loguru import logger

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

# Импорт базы данных
from database.core import init_db
# Импорт Middleware (Прослойка БД)
from middlewares.db import DbSessionMiddleware
# Импорт Хендлеров (Логика команд)
from handlers import common, admin_panel, user_flow, list_flow

# Загрузка настроек
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")

async def on_startup(bot: Bot):
    """Действия при старте бота"""
    logger.info("🏗 Проверка Базы Данных...")
    await init_db()
    logger.info("✅ База данных готова.")

    # Уведомление админов
    for admin_id in ADMIN_IDS:
        if admin_id:
            try:
                await bot.send_message(
                    chat_id=admin_id.strip(), 
                    text="🤖 <b>Бот успешно запущен!</b>\nСистема готова к работе."
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить старт админу {admin_id}: {e}")

async def main():
    # 1. Настройка логов
    logger.remove()
    logger.add(sys.stderr, level=LOG_LEVEL)
    logger.add("logs/bot.log", rotation="10 MB", level="DEBUG", compression="zip")

    if not BOT_TOKEN:
        logger.error("❌ Ошибка: BOT_TOKEN не найден в .env")
        return

    # 2. Инициализация
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 3. 🔌 ПОДКЛЮЧЕНИЕ MIDDLEWARE (Важно!)
    # Это автоматически дает доступ к БД в каждом хендлере
    dp.update.middleware(DbSessionMiddleware())

    # 4. 🔌 ПОДКЛЮЧЕНИЕ РОУТЕРОВ (Меню)
    dp.include_router(common.router)
    dp.include_router(admin_panel.router)
    dp.include_router(user_flow.router)
    dp.include_router(list_flow.router)

    # 5. Запуск
    dp.startup.register(on_startup)
    
    logger.info("🚀 Бот запускается...")
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
        logger.info("🛑 Бот остановлен")