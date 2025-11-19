from sqlalchemy import select, delete, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ShoppingList, CartItem, Product

class CartService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_list(self, user_id: int) -> ShoppingList | None:
        """Повертає активний список користувача."""
        stmt = select(ShoppingList).where(
            ShoppingList.user_id == user_id,
            ShoppingList.status == 'active'
        ).options(selectinload(ShoppingList.items)) # Одразу підвантажуємо товари
        
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_new_list(self, user_id: int) -> ShoppingList:
        """Створює новий чистий список. Якщо був старий - архівує/видаляє його."""
        # Спочатку закриваємо старі (м'яке видалення або архів)
        # Для простоти зараз просто міняємо статус старих на 'abandoned' (покинутий)
        # або видаляємо, якщо він порожній.
        
        old_list = await self.get_active_list(user_id)
        if old_list:
            old_list.status = 'abandoned'
        
        new_list = ShoppingList(user_id=user_id, status='active')
        self.session.add(new_list)
        await self.session.commit()
        return new_list

    async def add_item(self, user_id: int, sku: str, qty: int) -> dict:
        """
        Додає товар у список.
        Повертає: {'success': bool, 'message': str}
        """
        # 1. Отримуємо товар, щоб знати відділ
        stmt_prod = select(Product).where(Product.sku == sku)
        res_prod = await self.session.execute(stmt_prod)
        product = res_prod.scalar_one_or_none()
        
        if not product:
            return {'success': False, 'message': 'Товар не знайдено в базі.'}

        # 2. Отримуємо або створюємо список
        shopping_list = await self.get_active_list(user_id)
        if not shopping_list:
            shopping_list = ShoppingList(user_id=user_id, status='active')
            self.session.add(shopping_list)
            await self.session.flush() # Щоб отримати ID

        # 3. ПЕРЕВІРКА ВІДДІЛУ (Department Lock)
        # Якщо це перший товар - фіксуємо відділ
        if shopping_list.department_lock is None:
            # Якщо відділ порожній (None), ставимо "000"
            dept = product.department or "000"
            shopping_list.department_lock = dept
            await self.session.commit()
        
        # Якщо відділ вже зафіксовано, перевіряємо збіг
        current_dept = product.department or "000"
        if shopping_list.department_lock != current_dept:
            return {
                'success': False, 
                'message': f"⛔️ <b>Помилка відділу!</b>\nВи збираєте відділ <b>{shopping_list.department_lock}</b>.\nЦей товар з відділу <b>{current_dept}</b>.\n\nЗбережіть поточний список, щоб почати новий."
            }

        # 4. Додаємо товар (або оновлюємо кількість)
        # Шукаємо, чи є вже цей товар у списку
        stmt_item = select(CartItem).where(
            CartItem.list_id == shopping_list.id,
            CartItem.product_sku == sku
        )
        res_item = await self.session.execute(stmt_item)
        cart_item = res_item.scalar_one_or_none()

        if cart_item:
            cart_item.quantity += qty # Додаємо до існуючого
        else:
            cart_item = CartItem(
                list_id=shopping_list.id,
                product_sku=sku,
                quantity=qty
            )
            self.session.add(cart_item)
        
        await self.session.commit()
        return {'success': True, 'message': f"✅ Додано {qty} шт."}

    async def get_list_summary(self, user_id: int) -> tuple[ShoppingList | None, list]:
        """Повертає сам список і розширену інфу про товари (Join)"""
        shopping_list = await self.get_active_list(user_id)
        if not shopping_list:
            return None, []

        # Отримуємо позиції разом з даними про товар
        stmt = select(CartItem, Product).join(Product, CartItem.product_sku == Product.sku).where(
            CartItem.list_id == shopping_list.id
        )
        result = await self.session.execute(stmt)
        items = result.all() # Повертає список кортежів (CartItem, Product)
        return shopping_list, items

    async def clear_list(self, user_id: int):
        """Очищає поточний список (видаляє всі товари)"""
        shopping_list = await self.get_active_list(user_id)
        if shopping_list:
            # Видаляємо items
            stmt = delete(CartItem).where(CartItem.list_id == shopping_list.id)
            await self.session.execute(stmt)
            # Скидаємо блокування відділу
            shopping_list.department_lock = None
            await self.session.commit()