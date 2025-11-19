import re
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
# 👇 Імпортуємо func для підрахунку суми
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Product, ShoppingList, CartItem
from keyboards.inline import get_search_results_kb, get_product_card_kb, ProductCallback

router = Router()

class UserStates(StatesGroup):
    waiting_for_qty = State()

# --- 1. ПОШУК ТОВАРУ (ТЕКСТ) ---
@router.message(F.text & ~F.text.startswith('/'))
async def search_product(message: types.Message, session: AsyncSession):
    query = message.text.strip()
    
    # А. Якщо це Артикул (8 цифр)
    if re.fullmatch(r'\d{8}', query):
        await show_product_card(message, session, sku=query)
        return

    # Б. Текстовий пошук (SQL ILIKE)
    stmt = select(Product).where(
        or_(
            Product.name.ilike(f"%{query}%"),
            Product.sku.ilike(f"%{query}%")
        )
    ).where(Product.is_active == True).limit(10)
    
    result = await session.execute(stmt)
    products = result.scalars().all()

    if not products:
        await message.answer("🔍 На жаль, нічого не знайдено. Спробуйте інакше.")
        return

    if len(products) == 1:
        await show_product_card(message, session, sku=products[0].sku)
    else:
        await message.answer(
            f"🔍 Знайдено {len(products)} товарів:",
            reply_markup=get_search_results_kb(products)
        )

# --- 2. ВІДОБРАЖЕННЯ КАРТКИ (Функція) ---
async def show_product_card(message: types.Message, session: AsyncSession, sku: str, edit_msg_id: int = None, current_qty: int = 1):
    # Отримуємо товар
    stmt = select(Product).where(Product.sku == sku)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        text = "❌ Товар не знайдено (можливо, він був видалений)."
        if edit_msg_id:
            await message.bot.edit_message_text(text, chat_id=message.chat.id, message_id=edit_msg_id)
        else:
            await message.answer(text)
        return

    # -------------------------------------------------------
    # 🔥 ВИПРАВЛЕНИЙ ПІДРАХУНОК РЕЗЕРВІВ 🔥
    # -------------------------------------------------------
    # coalesce(sum(...), 0) гарантує, що ми отримаємо 0 замість None, якщо резервів немає
    stmt_reserved = (
        select(func.coalesce(func.sum(CartItem.quantity), 0))
        .select_from(CartItem) # Явно вказуємо таблицю
        .join(ShoppingList, CartItem.list_id == ShoppingList.id)
        .where(
            CartItem.product_sku == sku,
            ShoppingList.status == 'active'
        )
    )
    
    # Примусово оновлюємо сесію, щоб побачити зміни, зроблені в list_flow
    # await session.expire_all() 
    
    result_reserved = await session.execute(stmt_reserved)
    reserved_count = result_reserved.scalar()
    # -------------------------------------------------------

    # Рахуємо, скільки реально вільно
    available_qty = product.qty_total - reserved_count
    
    # Логіка надлишку
    surplus_text = ""
    if available_qty < 0:
        surplus = abs(available_qty)
        display_available = 0
        surplus_text = f"\n⚠️ <b>Надлишок: {surplus:g}</b>"
    else:
        display_available = available_qty

    status_icon = "✅" if display_available > 0 else "🔻"
    
    text = (
        f"📦 <b>{product.name}</b>\n"
        f"🆔 Артикул: <code>{product.sku}</code>\n"
        f"📂 Відділ: {product.department or '—'} | Група: {product.group or '—'}\n"
        f"⏳ Без руху: {product.months_inactive} міс.\n\n"
        f"💵 <b>Ціна:</b> {product.price:.2f} грн\n\n"
        f"📊 <b>Стан складу:</b>\n"
        f"📉 Залишок (БД): <b>{display_available:g}</b> {status_icon}\n"
        f"🔒 В резерві: <b>{reserved_count:g}</b>"
        f"{surplus_text}\n"
    )

    # Передаємо display_available для кнопки "Додати ВСЕ"
    kb = get_product_card_kb(sku, current_qty, max_qty=display_available)

    if edit_msg_id:
        try:
            await message.bot.edit_message_text(
                text=text, 
                chat_id=message.chat.id, 
                message_id=edit_msg_id, 
                reply_markup=kb
            )
        except Exception:
            pass # Текст не змінився, ігноруємо помилку Telegram
    else:
        await message.answer(text, reply_markup=kb)

# --- 3. ОБРОБКА КНОПОК (СТЕПЕР) ---
# Фільтр пропускає add/add_all далі до list_flow
@router.callback_query(ProductCallback.filter(F.action.not_in(["add", "add_all"])))
async def handle_stepper(callback: types.CallbackQuery, callback_data: ProductCallback, session: AsyncSession, state: FSMContext):
    action = callback_data.action
    qty = callback_data.qty
    sku = callback_data.sku

    if action == "show":
        await show_product_card(callback.message, session, sku=sku)
        await callback.answer()

    elif action == "inc":
        new_qty = qty + 1
        await show_product_card(callback.message, session, sku=sku, edit_msg_id=callback.message.message_id, current_qty=new_qty)
        await callback.answer()

    elif action == "dec":
        new_qty = max(1, qty - 1)
        await show_product_card(callback.message, session, sku=sku, edit_msg_id=callback.message.message_id, current_qty=new_qty)
        await callback.answer()

    elif action == "input":
        await callback.message.answer("⌨️ <b>Введіть кількість цифрами:</b>")
        await state.set_state(UserStates.waiting_for_qty)
        await state.update_data(sku=sku, msg_id=callback.message.message_id)
        await callback.answer()
    
    elif action == "photo":
        await callback.answer("Функція фото у розробці 📷")

# --- 4. ОБРОБКА РУЧНОГО ВВОДУ ЦИФРИ ---
@router.message(UserStates.waiting_for_qty)
async def process_manual_qty(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        qty = int(message.text)
        if qty < 1: raise ValueError
    except ValueError:
        await message.answer("⚠️ Будь ласка, введіть коректне число (більше 0).")
        return

    data = await state.get_data()
    sku = data.get('sku')
    
    # Оновлюємо картку
    await show_product_card(message, session, sku=sku, current_qty=qty)
    
    await state.clear()

@router.callback_query(F.data == "hide_card")
async def hide_card(callback: types.CallbackQuery):
    await callback.message.delete()