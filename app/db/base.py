"""Базові інтерфейси репозиторіїв та фабрика підключень до БД.

Тут будуть:
- абстрактні класи / протоколи для ItemsRepository, UserListsRepository тощо;
- функція, яка за DB_ENGINE з .env повертає конкретну реалізацію (sqlite / postgres ...).
"""
from typing import Protocol


class ItemsRepository(Protocol):
    """Інтерфейс роботи з товарами (items)."""

    async def get_by_sku(self, sku: str):
        ...

    async def upsert_from_import(self, items: list[dict]):
        ...


# Аналогічно будуть інтерфейси для UserListsRepository, ImportsRepository і т.д.
