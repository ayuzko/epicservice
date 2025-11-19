from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# --- ГЛАВНОЕ МЕНЮ (REPLY) ---
def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Генерирует нижнее меню.
    Кнопка 'Админ Панель' добавляется только если is_admin=True.
    """
    builder = ReplyKeyboardBuilder()

    # Ряд 1
    builder.row(
        KeyboardButton(text="🆕 Новий список"),
        KeyboardButton(text="📋 Мій список")
    )
    # Ряд 2
    builder.row(
        KeyboardButton(text="📊 Стан складу"),
        KeyboardButton(text="🕒 Історія")
    )
    
    # Ряд 3 (Только для админа)
    if is_admin:
        builder.row(KeyboardButton(text="🔐 АДМІН ПАНЕЛЬ"))

    return builder.as_markup(resize_keyboard=True)

# --- КНОПКА ОТМЕНЫ (УНИВЕРСАЛЬНАЯ) ---
def get_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Скасувати дію")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# --- АДМИН ПАНЕЛЬ (INLINE) ---
def get_admin_panel() -> InlineKeyboardMarkup:
    """
    Пульт управления админа.
    """
    builder = InlineKeyboardBuilder()

    # 1. Данные
    builder.row(InlineKeyboardButton(text="📥 Імпорт товарів", callback_data="admin_import"))
    
    # 2. Отчеты
    builder.row(
        InlineKeyboardButton(text="📉 Залишки (Excel)", callback_data="admin_export_stock"),
        InlineKeyboardButton(text="🚚 Зібране (Excel)", callback_data="admin_export_report")
    )
    
    # 3. Управление списками
    builder.row(
        InlineKeyboardButton(text="👥 Активні сесії", callback_data="admin_active_sessions"),
        InlineKeyboardButton(text="🗄 Архіви списків", callback_data="admin_list_archives")
    )
    
    # 4. Модерация и Настройки
    builder.row(
        InlineKeyboardButton(text="📷 Модерація фото", callback_data="admin_photo_mod"),
        InlineKeyboardButton(text="⚙️ Налаштування", callback_data="admin_settings")
    )
    
    # 5. Опасная зона и Массовые действия
    builder.row(
        InlineKeyboardButton(text="📢 Розсилка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="🗑 Очищення БД", callback_data="admin_wipe_db")
    )

    # 6. Выход
    builder.row(InlineKeyboardButton(text="🔙 Закрити панель", callback_data="admin_close_panel"))

    return builder.as_markup()

# --- ВЫБОР ПЕРИОДА ОТЧЕТА (INLINE) ---
def get_report_period_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 За сьогодні", callback_data="report_today"))
    builder.row(InlineKeyboardButton(text="🗓 За 3 дні", callback_data="report_3days"))
    builder.row(InlineKeyboardButton(text="📆 За тиждень", callback_data="report_week"))
    builder.row(InlineKeyboardButton(text="🔙 Скасувати", callback_data="admin_panel_back")) # Возврат в админку
    return builder.as_markup()