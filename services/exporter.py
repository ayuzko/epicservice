import io
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Product, ShoppingList, CartItem

class ExcelExporter:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- 1. ЕКСПОРТ ЗАЛИШКІВ (ДЛЯ АДМІНА) ---
    async def export_stock_balances(self) -> tuple[io.BytesIO, str]:
        """
        Генерує файл з усіма товарами, де залишок > 0.
        """
        # Отримуємо товари з бази
        stmt = select(Product).where(Product.qty_total > 0).order_by(Product.department, Product.name)
        result = await self.session.execute(stmt)
        products = result.scalars().all()

        # Формуємо дані для Pandas
        data = []
        for p in products:
            data.append({
                "Артикул": p.sku,
                "Назва": p.name,
                "Група": p.group,
                "Відділ": p.department,
                "Залишок": p.qty_total,
                "Ціна": p.price,
                "Сума": round(p.qty_total * p.price, 2),
                "Без руху (міс)": p.months_inactive
            })

        # Створюємо DataFrame
        if not data:
            # Якщо склад порожній, створюємо порожній DF з колонками
            df = pd.DataFrame(columns=["Артикул", "Назва", "Залишок"])
        else:
            df = pd.DataFrame(data)
        
        # Зберігаємо в буфер
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="Залишки")
            # Автоширина колонок
            self._adjust_column_width(writer.sheets["Залишки"], df)
        
        output.seek(0)
        filename = f"stock_balance_{datetime.now().strftime('%d.%m.%Y')}.xlsx"
        return output, filename

    # --- 2. ЕКСПОРТ СПИСКУ КОРИСТУВАЧА (SAVE) ---
    async def export_user_list(self, list_id: int) -> list[tuple[io.BytesIO, str]]:
        """
        Повертає список файлів (основний + надлишки, якщо є).
        Формат назви: Відділ_Юзер_Дата_Час.xlsx
        """
        # Отримуємо список з товарами та юзером
        stmt = select(ShoppingList).options(
            selectinload(ShoppingList.items).selectinload(CartItem.product),
            selectinload(ShoppingList.user)
        ).where(ShoppingList.id == list_id)
        
        result = await self.session.execute(stmt)
        shop_list = result.scalar_one_or_none()
        
        if not shop_list or not shop_list.items:
            return []

        # Підготовка даних
        main_data = []
        surplus_data = []
        
        # Розрахунок "на льоту" перед збереженням
        for item in shop_list.items:
            product = item.product
            qty_collected = item.quantity
            qty_db = product.qty_total
            
            # Логіка розподілу (Основний / Надлишок)
            if qty_collected <= qty_db:
                # Все в основний
                main_qty = qty_collected
                surplus_qty = 0
            else:
                # Розділяємо
                main_qty = qty_db # Забираємо все, що є на балансі
                surplus_qty = qty_collected - qty_db # Решта в надлишок
            
            # Запис в основний (якщо > 0)
            if main_qty > 0:
                main_data.append({
                    "Артикул": product.sku,
                    "Назва": product.name,
                    "Кількість": main_qty,
                    "Ціна": product.price,
                    "Сума": round(main_qty * product.price, 2)
                })
                # Оновлюємо залишок в БД (списуємо)
                product.qty_total -= main_qty

            # Запис в надлишок
            if surplus_qty > 0:
                surplus_data.append({
                    "Артикул": product.sku,
                    "Назва": product.name,
                    "Кількість": surplus_qty,
                    "Ціна": product.price,
                    "Сума": round(surplus_qty * product.price, 2)
                })
                # Зберігаємо факт надлишку в історії
                item.surplus_quantity = surplus_qty
                item.quantity = main_qty # В історії записуємо "офіційну" кількість
            
        # Генеруємо ім'я файлу
        dept = shop_list.department_lock or "000"
        # Очищаємо ім'я від спецсимволів
        username = shop_list.user.fullname or f"User{shop_list.user_id}"
        username = "".join([c for c in username if c.isalnum() or c in (' ', '_', '-')]).strip()
        
        timestamp = datetime.now().strftime("%d.%m.%y_%H.%M")
        
        base_filename = f"{dept}_{username}_{timestamp}"
        files_to_send = []

        # 1. Основний файл
        if main_data:
            output1 = io.BytesIO()
            df1 = pd.DataFrame(main_data)
            with pd.ExcelWriter(output1, engine='openpyxl') as writer:
                df1.to_excel(writer, index=False)
                self._adjust_column_width(writer.sheets["Sheet1"], df1)
            output1.seek(0)
            files_to_send.append((output1, f"{base_filename}.xlsx"))

        # 2. Файл надлишків
        if surplus_data:
            output2 = io.BytesIO()
            df2 = pd.DataFrame(surplus_data)
            with pd.ExcelWriter(output2, engine='openpyxl') as writer:
                df2.to_excel(writer, index=False)
                self._adjust_column_width(writer.sheets["Sheet1"], df2)
            output2.seek(0)
            files_to_send.append((output2, f"НАДЛИШКИ_{base_filename}.xlsx"))

        # Фіналізація списку в БД
        shop_list.status = 'saved'
        await self.session.commit()

        return files_to_send

    # --- 3. ЗВІТ "ЗІБРАНЕ" (АНАЛІТИКА) ---
    async def export_analytics(self, days: int) -> tuple[io.BytesIO, str]:
        """
        Звіт по тому, що юзери назбирали за період.
        """
        start_date = datetime.now() - timedelta(days=days)
        
        # Вибираємо тільки збережені списки
        stmt = select(CartItem).join(ShoppingList).join(Product).where(
            ShoppingList.status == 'saved',
            ShoppingList.updated_at >= start_date
        ).options(selectinload(CartItem.product), selectinload(CartItem.shopping_list).selectinload(ShoppingList.user))
        
        result = await self.session.execute(stmt)
        items = result.scalars().all()
        
        data = []
        for item in items:
            p = item.product
            u = item.shopping_list.user
            data.append({
                "Дата": item.shopping_list.updated_at.strftime("%d.%m.%Y %H:%M"),
                "Користувач": u.fullname,
                "Відділ": item.shopping_list.department_lock,
                "Артикул": p.sku,
                "Назва": p.name,
                "Кількість": item.quantity,
                "Надлишок": item.surplus_quantity,
                "Сума": round(item.quantity * p.price, 2)
            })
            
        if not data:
            df = pd.DataFrame(columns=["Дата", "Користувач", "Артикул", "Назва", "Кількість"])
        else:
            df = pd.DataFrame(data)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
            self._adjust_column_width(writer.sheets["Sheet1"], df)
        
        output.seek(0)
        filename = f"analytics_{days}days_{datetime.now().strftime('%d.%m')}.xlsx"
        return output, filename

    def _adjust_column_width(self, worksheet, df):
        """Автоширина колонок для краси"""
        for column in df:
            column_length = max(df[column].astype(str).map(len).max(), len(column))
            col_idx = df.columns.get_loc(column) + 1
            # openpyxl access by column letter/index
            worksheet.column_dimensions[chr(64 + col_idx)].width = column_length + 2