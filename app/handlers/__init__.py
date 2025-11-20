# app/handlers/__init__.py

from __future__ import annotations

from aiogram import Dispatcher

# Роутери користувача
# Додаємо імпорт carousel
from app.handlers.user import item_card, main_menu, carousel

# Роутери адміна
from app.handlers.admin import import_excel, admin_menu


def register_user_handlers(dp: Dispatcher) -> None:
    """
    Реєструє всі роутери, пов'язані з роботою звичайного користувача.
    """
    dp.include_router(main_menu.router)
    dp.include_router(item_card.router)
    # Підключаємо роутер каруселі
    dp.include_router(carousel.router)


def register_admin_handlers(dp: Dispatcher) -> None:
    """
    Реєструє всі роутери адмінської частини (імпорт, адмін‑панель тощо).
    """
    dp.include_router(admin_menu.router)
    dp.include_router(import_excel.router)


def register_all_handlers(dp: Dispatcher) -> None:
    """
    Головна точка реєстрації всіх роутерів у застосунку.

    Викликається з main.py один раз при старті.
    """
    register_user_handlers(dp)
    register_admin_handlers(dp)