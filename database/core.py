import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from dotenv import load_dotenv
from database.models import Base

# Загружаем настройки из .env
load_dotenv()

# 1. Получаем адрес БД
# Сначала ищем POSTGRES, если нет - берем LITE
DB_URL = os.getenv("DB_POSTGRES") or os.getenv("DB_LITE")

if not DB_URL:
    raise ValueError("❌ CRITICAL ERROR: DB_URL не найден в .env файле!")

# 2. Создаем Движок (Engine)
# Это точка входа в базу данных
engine = create_async_engine(
    DB_URL,
    echo=False, # Поставь True, если хочешь видеть SQL запросы в консоли (для отладки)
    future=True
)

# 3. Фабрика сессий
# Именно через неё мы будем делать запросы в коде
async_session_maker = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# --- ФУНКЦИИ УПРАВЛЕНИЯ ---

async def init_db():
    """
    Создает таблицы при старте, если их нет.
    """
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Раскомментируй, чтобы удалить БД (WIPE)
        await conn.run_sync(Base.metadata.create_all)
        print("✅ База данных проверена/создана.")

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии.
    Используется в хендлерах: async def my_handler(session: AsyncSession = Depends(get_session))
    """
    async with async_session_maker() as session:
        yield session