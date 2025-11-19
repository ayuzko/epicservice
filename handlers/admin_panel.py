import io
from aiogram import Router, F, types, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.repo import UserRepo
from services.importer import SmartImporter
from keyboards.menus import get_admin_panel

# Определение состояний (режимов работы)
class AdminStates(StatesGroup):
    waiting_for_import_file = State()

router = Router()

# --- 1. ВХОД В ПАНЕЛЬ ---
@router.message(F.text == "🔐 АДМІН ПАНЕЛЬ")
async def open_admin_panel(message: types.Message, session: AsyncSession):
    repo = UserRepo(session)
    user = await repo.get_user(message.from_user.id)
    
    if not user or user.role != "admin":
        await message.answer("⛔️ У вас немає прав адміністратора.")
        return

    await message.answer(
        "🔓 <b>Панель Адміністратора</b>\nВиберіть дію:",
        reply_markup=get_admin_panel()
    )

# --- 2. НАЖАТИЕ "ИМПОРТ" ---
@router.callback_query(F.data == "admin_import")
async def start_import_flow(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer() # Убираем часики загрузки
    
    await callback.message.answer(
        "📥 <b>Режим Імпорту</b>\n\n"
        "Будь ласка, надішліть файл <code>.xlsx</code> або <code>.csv</code>.\n"
        "Бот спробує автоматично розпізнати колонки.\n\n"
        "❌ <i>Напишіть 'відміна' або натисніть кнопку в меню для скасування.</i>"
    )
    # Включаем режим ожидания файла
    await state.set_state(AdminStates.waiting_for_import_file)

# --- 3. ПОЛУЧЕНИЕ ФАЙЛА И ЗАПУСК ИМПОРТА ---
@router.message(AdminStates.waiting_for_import_file, F.document)
async def process_import_file(message: types.Message, state: FSMContext, bot: Bot, session: AsyncSession):
    # Проверка расширения
    doc = message.document
    if not doc.file_name.lower().endswith(('.xlsx', '.xls', '.csv')):
        await message.answer("⚠️ Будь ласка, надішліть файл Excel або CSV.")
        return

    status_msg = await message.answer("⏳ <b>Завантаження та аналіз файлу...</b>")

    try:
        # 1. Скачиваем файл в оперативную память (без сохранения на диск)
        file_in_io = io.BytesIO()
        await bot.download(doc, destination=file_in_io)
        
        # 2. Запускаем Smart Importer
        importer = SmartImporter(session)
        
        # Сначала анализируем (тут можно было бы добавить шаг с маппингом, но пока сразу импортируем)
        # Если хочешь проверку колонок перед импортом - скажи, допишем.
        stats = await importer.run_import(file_in_io, doc.file_name)
        
        # 3. Отчет
        report_text = (
            f"✅ <b>Імпорт успішно завершено!</b>\n\n"
            f"🆕 Створено: <b>{stats['created']}</b>\n"
            f"♻️ Оновлено: <b>{stats['updated']}</b>\n"
            f"💤 Приховано (немає в файлі): <b>{stats['deactivated']}</b>\n"
            f"❌ Помилок: <b>{stats['errors']}</b>"
        )
        
        await status_msg.edit_text(report_text)
        
    except Exception as e:
        await status_msg.edit_text(f"💥 <b>Критична помилка імпорту:</b>\n{str(e)}")
    finally:
        # Выключаем режим ожидания
        await state.clear()

# --- 4. ВЫХОД / ОТМЕНА ---
@router.callback_query(F.data == "admin_close_panel")
async def close_panel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer("Панель закрито")