from aiogram import Router, F, types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cart import CartService
from keyboards.inline import ProductCallback, get_my_list_kb
from database.models import Product

# Імпортуємо show_product_card, щоб оновлювати картку
from handlers.user_flow import show_product_card

router = Router()

# --- 1. НОВИЙ СПИСОК ---
@router.message(F.text == "🆕 Новий список")
async def cmd_new_list(message: types.Message, session: AsyncSession):
    service = CartService(session)
    await service.create_new_list(message.from_user.id)
    await message.answer("🆕 <b>Новий список створено!</b>\nМожна сканувати товари.")

# --- 2. ДОДАВАННЯ (ЗВИЧАЙНЕ + ДОДАТИ ВСЕ) ---
@router.callback_query(ProductCallback.filter(F.action.in_(["add", "add_all"])))
async def process_add_to_cart(callback: types.CallbackQuery, callback_data: ProductCallback, session: AsyncSession):
    service = CartService(session)
    user_id = callback.from_user.id
    sku = callback_data.sku
    action = callback_data.action
    
    # Визначаємо кількість
    qty_to_add = callback_data.qty

    # Якщо "Додати ВСЕ", треба дізнатися залишок
    if action == "add_all":
        # Отримуємо товар, щоб дізнатись залишок
        stmt = select(Product).where(Product.sku == sku)
        res = await session.execute(stmt)
        product = res.scalar_one_or_none()
        if product:
             # Тут можна додати перевірку резервів, щоб не брати більше ніж вільно
             # Але поки беремо "в тупу" загальний залишок, а надлишки порахуються при збереженні
             qty_to_add = int(product.qty_total)
             if qty_to_add <= 0:
                 await callback.answer("⚠️ Товар відсутній на балансі!", show_alert=True)
                 return
        else:
            await callback.answer("❌ Помилка товару", show_alert=True)
            return

    # Додаємо в БД
    result = await service.add_item(user_id, sku, qty_to_add)
    
    if result['success']:
        # 1. Показуємо повідомлення
        await callback.answer(f"✅ Додано: {qty_to_add} шт.", show_alert=False)
        
        # 2. ОНОВЛЮЄМО КАРТКУ (Щоб цифри резерву змінилися)
        # Ми викликаємо функцію з user_flow, яка перемалює повідомлення
        await show_product_card(
            callback.message, 
            session, 
            sku=sku, 
            edit_msg_id=callback.message.message_id,
            current_qty=1 # Скидаємо лічильник на 1 після додавання
        )
    else:
        await callback.answer(text=result['message'], show_alert=True)

# --- 3. ПЕРЕГЛЯД СПИСКУ ---
@router.message(F.text == "📋 Мій список")
async def show_my_list(message: types.Message, session: AsyncSession):
    service = CartService(session)
    shopping_list, items = await service.get_list_summary(message.from_user.id)
    
    if not shopping_list or not items:
        await message.answer("📭 <b>Список порожній.</b>")
        return

    lines = [f"📋 <b>Ваш список (Відділ {shopping_list.department_lock}):</b>\n"]
    total_qty, total_sum = 0, 0.0
    
    for idx, (item, product) in enumerate(items, start=1):
        row_sum = item.quantity * product.price
        total_qty += item.quantity
        total_sum += row_sum
        
        surplus_text = ""
        if item.quantity > product.qty_total:
            surplus = item.quantity - product.qty_total
            surplus_text = f" ⚠️ (+{surplus:.0f})"
        
        lines.append(
            f"{idx}. <b>{product.name[:25]}..</b> ({product.sku})\n"
            f"   └ {item.quantity:.0f} шт. x {product.price:.1f} = <b>{row_sum:.1f}</b>{surplus_text}"
        )

    lines.append(f"\n📦 Всього: {total_qty:.0f} шт. | 💰 {total_sum:.2f} грн")
    await message.answer("\n".join(lines), reply_markup=get_my_list_kb(shopping_list.id))

@router.callback_query(F.data.startswith("clear_list_"))
async def clear_current_list(callback: types.CallbackQuery, session: AsyncSession):
    service = CartService(session)
    await service.clear_list(callback.from_user.id)
    await callback.message.edit_text("🗑 <b>Список очищено.</b>")

@router.callback_query(F.data.startswith("save_list_"))
async def save_current_list(callback: types.CallbackQuery):
    await callback.answer("Функція експорту в наступному кроці...", show_alert=True)