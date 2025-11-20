# app/db/session.py

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config.settings import Settings

settings = Settings()

# Если используется sqlite, нужно добавить драйвер aiosqlite для асинхронности
db_url = settings.DB_URL
if db_url.startswith("sqlite://") and "aiosqlite" not in db_url:
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")

engine = create_async_engine(
    db_url,
    echo=False,  # Ставьте True для отладки SQL запросов
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_db() -> AsyncSession:
    """Dependency для получения сессии БД."""
    async with AsyncSessionLocal() as session:
        yield session