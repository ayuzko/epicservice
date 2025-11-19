import os
from aiogram import Router, F, types, Bot
from aiogram.filters import CommandStart, Command
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

from database.repo import UserRepo
from keyboards.menus import get_main_menu

load_dotenv()
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",")

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, session: AsyncSession, bot: Bot):
    """
    Точка входу. Перевіряє права доступу.
    """
    user_id = message.from_user.id
    
    # 1. Ініціалізуємо Репозиторій (робота з БД)
    repo = UserRepo(session)
    
    # 2. Отримуємо користувача з бази
    user = await repo.get_user(user_id)
    
    # 3. Перевірка: Чи є користувач в .env як Супер-Адмін?
    # Якщо так - автоматично робимо його адміном в базі
    is_super_admin = str(user_id) in ADMIN_IDS
    
    if not user:
        # --- СЦЕНАРІЙ: НОВАЧОК ---
        role = "admin" if is_super_admin else "pending"
        
        await repo.add_user(
            telegram_id=user_id,
            fullname=message.from_user.full_name,
            username=message.from_user.username,
            role=role
        )
        
        if role == "admin":
            await message.answer(
                "👨‍💻 **Вітаю, Адміністратор!**\nБазу налаштовано, доступ відкрито.",
                reply_markup=get_main_menu(is_admin=True)
            )
        else:
            # Сповіщення адмінам про новачків
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"🔔 <b>Нова заявка!</b>\nUser: {message.from_user.full_name}\nID: <code>{user_id}</code>\nUsername: @{message.from_user.username}"
                    )
                except:
                    pass

            await message.answer(
                "✋ <b>Доступ обмежено.</b>\n\nЦе корпоративний бот. Вашу заявку надіслано адміністратору.\nБудь ласка, зачекайте на підтвердження."
            )
            
    else:
        # --- СЦЕНАРІЙ: ВЖЕ В БАЗІ ---
        
        # Оновлюємо роль, якщо раптом став адміном в .env
        if is_super_admin and user.role != "admin":
            await repo.update_role(user_id, "admin")
            user.role = "admin"

        if user.role == "banned":
            await message.answer("⛔️ <b>Ваш акаунт заблоковано.</b>")
            return

        if user.role == "pending":
            await message.answer("⏳ <b>Заявка на розгляді.</b>\nАдміністратор ще не надав вам доступ.")
            return

        # ВСЕ ОК - Показуємо меню
        is_admin = (user.role == "admin")
        await message.answer(
            f"👋 Привіт, <b>{message.from_user.first_name}</b>!\nСклад готовий до роботи.",
            reply_markup=get_main_menu(is_admin=is_admin)
        )

@router.message(Command("id"))
async def cmd_id(message: types.Message):
    await message.answer(f"🆔 Ваш Telegram ID: <code>{message.from_user.id}</code>")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📘 <b>Довідка</b>\n\n"
        "• <b>Пошук:</b> Просто надішліть Артикул (8 цифр) або Назву товару.\n"
        "• <b>Новий список:</b> Почати збір товарів.\n"
        "• <b>Мій список:</b> Переглянути, що ви набрали.\n"
        "• <b>+Фото:</b> Додати фото до товару.\n"
        "\n⚠️ <i>Якщо щось зламалось - пишіть адміністратору.</i>"
    )
    await message.answer(text)