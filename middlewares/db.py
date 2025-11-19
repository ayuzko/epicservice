from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

# Імпортуємо нашу фабрику сесій
from database.core import async_session_maker

class DbSessionMiddleware(BaseMiddleware):
    """
    Цей мідлвар автоматично відкриває сесію БД перед обробкою повідомлення
    і закриває її після.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Відкриваємо сесію
        async with async_session_maker() as session:
            # Кладемо сесію в дані, які летять у хендлер
            data["session"] = session
            
            # Запускаємо хендлер (обробку команди)
            result = await handler(event, data)
            
            # Після виходу з хендлера сесія закриється автоматично (context manager)
            return result