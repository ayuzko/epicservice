from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

# --- ФАБРИКА ДАНИХ (Щоб не плутатись у рядках) ---
class ProductCallback(CallbackData, prefix="prod"):
    sku: str
    action: str # 'inc', 'dec', 'input', 'add', 'photo'
    qty: int # Поточне число на лічильнику

# --- СПИСОК ЗНАЙДЕНИХ ТОВАРІВ ---
def get_search_results_kb(products: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        # Кнопка: "Коньяк Коблево (616...)"
        builder.row(InlineKeyboardButton(
            text=f"{p.name[:30]}... ({p.sku})", 
            callback_data=ProductCallback(sku=p.sku, action="show", qty=1).pack()
        ))
    return builder.as_markup()

# --- КАРТКА ТОВАРУ (СТЕПЕР) ---
def get_product_card_kb(sku: str, current_qty: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Ряд 1: [-] [ 1 ] [+]
    # Захист: не можна зробити менше 1
    btn_dec = InlineKeyboardButton(
        text="➖", 
        callback_data=ProductCallback(sku=sku, action="dec", qty=current_qty).pack()
    )
    btn_count = InlineKeyboardButton(
        text=f"📦 {current_qty} шт.", 
        callback_data="ignore" # Просто візуальна кнопка
    )
    btn_inc = InlineKeyboardButton(
        text="➕", 
        callback_data=ProductCallback(sku=sku, action="inc", qty=current_qty).pack()
    )
    
    builder.row(btn_dec, btn_count, btn_inc)

    # Ряд 2: Підтвердити (Додати в список)
    builder.row(InlineKeyboardButton(
        text=f"📥 Додати в список ({current_qty})", 
        callback_data=ProductCallback(sku=sku, action="add", qty=current_qty).pack()
    ))

    # Ряд 3: Ввести вручну | +Фото
    builder.row(
        InlineKeyboardButton(text="⌨️ Ввести вручну", callback_data=ProductCallback(sku=sku, action="input", qty=current_qty).pack()),
        InlineKeyboardButton(text="📷 +Фото", callback_data=ProductCallback(sku=sku, action="photo", qty=current_qty).pack())
    )
    
    # Ряд 4: Закрити (щоб не смітити в чаті)
    builder.row(InlineKeyboardButton(text="❌ Приховати", callback_data="hide_card"))

    return builder.as_markup()

# --- МЕНЮ "МІЙ СПИСОК" ---
def get_my_list_kb(list_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Головна дія - Зберегти
    builder.row(InlineKeyboardButton(
        text="💾 ЗБЕРЕГТИ ТА ВИВАНТАЖИТИ", 
        callback_data=f"save_list_{list_id}"
    ))
    
    # Додаткові дії
    builder.row(
        # InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit_list_{list_id}"), # На майбутнє
        InlineKeyboardButton(text="🗑 Видалити все", callback_data=f"clear_list_{list_id}")
    )
    
    # Закрити
    builder.row(InlineKeyboardButton(text="🔙 Приховати", callback_data="hide_card"))
    
    return builder.as_markup()