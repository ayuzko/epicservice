from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

# --- ФАБРИКА ДАНИХ ---
class ProductCallback(CallbackData, prefix="prod"):
    sku: str
    action: str # 'inc', 'dec', 'input', 'add', 'add_all', 'photo'
    qty: int

# --- СПИСОК ЗНАЙДЕНИХ ---
def get_search_results_kb(products: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(InlineKeyboardButton(
            text=f"{p.name[:30]}... ({p.sku})", 
            callback_data=ProductCallback(sku=p.sku, action="show", qty=1).pack()
        ))
    return builder.as_markup()

# --- КАРТКА ТОВАРУ (ОНОВЛЕНА) ---
def get_product_card_kb(sku: str, current_qty: int = 1, max_qty: float = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Ряд 1: [-] [ 📥 1 шт. ] [+]
    # Середня кнопка тепер ДОДАЄ товар
    btn_dec = InlineKeyboardButton(
        text="➖", 
        callback_data=ProductCallback(sku=sku, action="dec", qty=current_qty).pack()
    )
    btn_add = InlineKeyboardButton(
        text=f"📥 Додати {current_qty} шт.", 
        callback_data=ProductCallback(sku=sku, action="add", qty=current_qty).pack()
    )
    btn_inc = InlineKeyboardButton(
        text="➕", 
        callback_data=ProductCallback(sku=sku, action="inc", qty=current_qty).pack()
    )
    
    builder.row(btn_dec, btn_add, btn_inc)

    # Ряд 2: [ 📦 Додати ВСЕ (10 шт.) ]
    # Показуємо, якщо на складі щось є
    if max_qty > 0:
        builder.row(InlineKeyboardButton(
            text=f"📦 Додати ВСЕ ({max_qty:g} шт.)", 
            callback_data=ProductCallback(sku=sku, action="add_all", qty=0).pack()
        ))

    # Ряд 3: Ввести вручну | +Фото
    builder.row(
        InlineKeyboardButton(text="⌨️ Вручну", callback_data=ProductCallback(sku=sku, action="input", qty=current_qty).pack()),
        InlineKeyboardButton(text="📷 +Фото", callback_data=ProductCallback(sku=sku, action="photo", qty=current_qty).pack())
    )
    
    # Ряд 4: Закрити
    builder.row(InlineKeyboardButton(text="❌ Приховати", callback_data="hide_card"))

    return builder.as_markup()

# --- МЕНЮ "МІЙ СПИСОК" ---
def get_my_list_kb(list_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💾 ЗБЕРЕГТИ ТА ВИВАНТАЖИТИ", callback_data=f"save_list_{list_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Видалити все", callback_data=f"clear_list_{list_id}"))
    builder.row(InlineKeyboardButton(text="🔙 Приховати", callback_data="hide_card"))
    return builder.as_markup()