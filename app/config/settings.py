# app/config/settings.py

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Базові налаштування застосунку (читаються з .env).

    Pydantic v2: BaseSettings тепер у пакеті pydantic-settings,
    а конфіг задається через model_config.
    """

    BOT_TOKEN: str = Field(..., description="Telegram Bot API token")

    DB_ENGINE: str = Field(
        "sqlite",
        description="Тип БД: sqlite / postgres / mysql",
    )

    DB_URL: str = Field(
        "sqlite:///data/bot.db",
        description="Рядок підключення до БД (для sqlite — шлях до файлу)",
    )

    # Рядок з ID адмінів (через кому) з .env:
    # TELEGRAM_ADMIN_IDS=1962821395,123456789
    TELEGRAM_ADMIN_IDS: str | None = Field(
        default=None,
        description="Список Telegram ID адміністраторів (через кому)",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ігнорувати зайві змінні в .env
    )
