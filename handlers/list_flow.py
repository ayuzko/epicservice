from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from services.cart import CartService
from keyboards.inline import ProductCallback, get_my_list_kb

router = Router()

# --- 1. НОВИЙ СПИСОК ---
@router.message(F.text == "🆕 Новий список")
async def cmd_new_list(message: types.Message, session: AsyncSession):
    service = CartService(session)
    
    # Створюємо новий (старий архівується автоматом всередині сервісу)
    new_list = await service.create_new_list(message.from_user.id)
    
    await message.answer(
        "🆕 <b>Новий список створено!</b>\n\n"
        "1. Знайдіть товар (пошук/скан).\n"
        "2. Додайте його в список.\n"
        "3. ⚠️ <b>Пам'ятайте:</b> список прив'язується до відділу першого доданого товару."
    )

# --- 2. ДОДАВАННЯ ТОВАРУ (КНОПКА В КАРТЦІ) ---
@router.callback_query(ProductCallback.filter(F.action == "add"))
async def add_product_to_cart(callback: types.CallbackQuery, callback_data: ProductCallback, session: AsyncSession):
    service = CartService(session)
    user_id = callback.from_user.id
    sku = callback_data.sku
    qty = callback_data.qty

    # Викликаємо сервіс
    result = await service.add_item(user_id, sku, qty)
    
    if result['success']:
        # Успіх - показуємо спливаюче вікно (Alert)
        await callback.answer(
            text=f"✅ Додано: {qty} шт.\nТовар у списку!",
            show_alert=False # False = просто текст вгорі, True = вікно з кнопкою ОК
        )
    else:
        # Помилка (наприклад, інший відділ) - показуємо вікно з помилкою
        await callback.answer(
            text=result['message'],
            show_alert=True 
        )

# --- 3. ПЕРЕГЛЯД СПИСКУ ("МІЙ СПИСОК") ---
@router.message(F.text == "📋 Мій список")
async def show_my_list(message: types.Message, session: AsyncSession):
    service = CartService(session)
    user_id = message.from_user.id
    
    shopping_list, items = await service.get_list_summary(user_id)
    
    if not shopping_list:
        await message.answer("📭 <b>Ваш список порожній.</b>\nНатисніть '🆕 Новий список', щоб почати.")
        return

    if not items:
        await message.answer(f"📭 <b>Список активний (Відділ {shopping_list.department_lock}), але порожній.</b>")
        return

    # Формуємо текст чека
    # Ліміт Телеграм повідомлення ~4000 символів. Якщо товарів >50, треба ділити.
    # Поки зробимо просту версію.
    
    lines = []
    total_qty = 0
    total_sum = 0.0
    
    lines.append(f"📋 <b>Ваш список (Відділ {shopping_list.department_lock}):</b>\n")
    
    for idx, (item, product) in enumerate(items, start=1):
        # Розрахунок суми рядка
        row_sum = item.quantity * product.price
        total_qty += item.quantity
        total_sum += row_sum
        
        # Перевірка на надлишок (візуальна)
        surplus_text = ""
        if item.quantity > product.qty_total:
            surplus = item.quantity - product.qty_total
            surplus_text = f" ⚠️ <b>(+{surplus:.0f})</b>"
        
        lines.append(
            f"{idx}. <b>{product.name[:30]}..</b> ({product.sku})\n"
            f"   └ {item.quantity:.0f} шт. x {product.price:.1f} грн = <b>{row_sum:.1f}</b>{surplus_text}"
        )

    lines.append("\n" + "—" * 15)
    lines.append(f"📦 <b>Всього:</b> {total_qty:.0f} шт.")
    lines.append(f"💰 <b>Сума:</b> {total_sum:.2f} грн")
    
    text = "\n".join(lines)
    
    await message.answer(text, reply_markup=get_my_list_kb(shopping_list.id))

# --- 4. ОЧИСТКА СПИСКУ ---
@router.callback_query(F.data.startswith("clear_list_"))
async def clear_current_list(callback: types.CallbackQuery, session: AsyncSession):
    service = CartService(session)
    await service.clear_list(callback.from_user.id)
    
    await callback.message.edit_text("🗑 <b>Список очищено.</b>")
    await callback.answer()

# --- 5. ЗБЕРЕЖЕННЯ (ЗАГЛУШКА) ---
@router.callback_query(F.data.startswith("save_list_"))
async def save_current_list(callback: types.CallbackQuery, session: AsyncSession):
    # Цей функціонал ми напишемо на наступному кроці (Експорт Excel)
    await callback.answer("⏳ Функція генерації файлів у розробці...", show_alert=True)