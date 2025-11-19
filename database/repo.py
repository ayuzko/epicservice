from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, BotSetting

class UserRepo:
    """
    Всі операції з користувачами (Check, Ban, Approve).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def user_exists(self, telegram_id: int) -> bool:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_user(self, telegram_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_user(self, telegram_id: int, fullname: str = None, username: str = None, role: str = "pending"):
        """Реєструє нового користувача."""
        # Защита от дублей
        if await self.user_exists(telegram_id):
            return
        
        new_user = User(
            telegram_id=telegram_id,
            fullname=fullname,
            username=username,
            role=role
        )
        self.session.add(new_user)
        await self.session.commit()

    async def update_role(self, telegram_id: int, new_role: str):
        """Змінює роль (admin, user, banned)."""
        stmt = update(User).where(User.telegram_id == telegram_id).values(role=new_role)
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_admins(self) -> list[int]:
        """Повертає список ID всіх адмінів."""
        stmt = select(User.telegram_id).where(User.role == "admin")
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

class SettingsRepo:
    """
    Робота з налаштуваннями (BotSetting).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_setting(self, key: str, default: str = None) -> str:
        stmt = select(BotSetting).where(BotSetting.key == key)
        result = await self.session.execute(stmt)
        obj = result.scalar_one_or_none()
        return obj.value if obj else default

    async def set_setting(self, key: str, value: str, description: str = None):
        # Upsert (Оновити або Вставити)
        stmt = select(BotSetting).where(BotSetting.key == key)
        result = await self.session.execute(stmt)
        obj = result.scalar_one_or_none()

        if obj:
            obj.value = str(value)
        else:
            self.session.add(BotSetting(key=key, value=str(value), description=description))
        
        await self.session.commit()