import re
import io
import pandas as pd
from typing import Dict, List, Tuple, Any
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Product, ImportMapping

# --- СТАРТОВЫЙ СЛОВАРЬ СИНОНИМОВ ---
# Бот будет использовать его, если в БД пусто.
# Это покрывает 99% твоих файлов.
DEFAULT_MAPPING = {
    'sku': ['а', 'арт', 'артикул', 'sku', 'код', 'code', 'id', 'item_no'],
    'name': ['н', 'назва', 'название', 'name', 'title', 'description', 'товар'],
    'qty_total': ['к', 'кол', 'кол-во', 'кількість', 'залишок', 'qty', 'quantity', 'count'],
    'price': ['ц', 'ціна', 'цена', 'price', 'cost'],
    'total_sum': ['с', 'сума', 'сумма', 'sum', 'total', 'вартість', 'money'],
    'group': ['г', 'гр', 'група', 'группа', 'group', 'category', 'cat'],
    'department': ['в', 'від', 'відділ', 'отдел', 'dept', 'department'],
    'months_inactive': ['м', 'міс', 'мес', 'місяців', 'months', 'period']
}

class SmartImporter:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _normalize_header(self, header: str) -> str:
        """Очищает заголовок от мусора: ' Залишок (шт) ' -> 'залишок'"""
        return str(header).lower().strip().split('(')[0].strip()

    async def get_db_mapping(self) -> Dict[str, str]:
        """Загружает словарь из БД (если админ учил бота)"""
        stmt = select(ImportMapping)
        result = await self.session.execute(stmt)
        mappings = result.scalars().all()
        return {m.original_header: m.target_field for m in mappings}

    def _detect_column(self, header: str, db_map: Dict[str, str]) -> str | None:
        """Пытается понять, что это за колонка"""
        norm_header = self._normalize_header(header)
        
        # 1. Проверка по БД (точный выбор Админа)
        if norm_header in db_map:
            return db_map[norm_header]
        
        # 2. Проверка по встроенному словарю (Defaults)
        for field, synonyms in DEFAULT_MAPPING.items():
            # Полное совпадение ('кол' == 'кол')
            if norm_header in synonyms:
                return field
            # Частичное ('залишок на складі' -> 'залишок')
            for syn in synonyms:
                if syn == norm_header: # Строгое
                    return field
        
        return None

    async def read_file_to_df(self, file_bytes: io.BytesIO, filename: str) -> pd.DataFrame:
        """Читает любой Excel/CSV в Pandas DataFrame"""
        filename = filename.lower()
        try:
            if filename.endswith('.csv'):
                # Пытаемся угадать разделитель
                try:
                    df = pd.read_csv(file_bytes, sep=None, engine='python')
                except:
                    file_bytes.seek(0)
                    df = pd.read_csv(file_bytes, sep=',')
            else:
                # Excel
                df = pd.read_excel(file_bytes)
            
            # Очистка названий колонок (strip)
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            logger.error(f"Ошибка чтения файла: {e}")
            raise ValueError("Не вдалося прочитати файл. Перевірте формат.")

    async def analyze_columns(self, file_bytes: io.BytesIO, filename: str) -> List[str]:
        """
        ШАГ 1: Возвращает список колонок, которые бот НЕ понял.
        Если список пустой -> можно делать импорт.
        """
        df = await self.read_file_to_df(file_bytes, filename)
        db_map = await self.get_db_mapping()
        
        unknown_headers = []
        for col in df.columns:
            field = self._detect_column(col, db_map)
            if not field:
                # Игнорируем пустые колонки "Unnamed: 0"
                if "unnamed" not in str(col).lower():
                    unknown_headers.append(col)
        
        return unknown_headers

    async def run_import(self, file_bytes: io.BytesIO, filename: str) -> Dict[str, int]:
        """
        ШАГ 2: Полный цикл импорта и обновления БД.
        """
        # 1. Подготовка
        df = await self.read_file_to_df(file_bytes, filename)
        db_map = await self.get_db_mapping()
        
        # Переименовываем колонки в наши внутренние имена (sku, price...)
        rename_map = {}
        for col in df.columns:
            field = self._detect_column(col, db_map)
            if field:
                rename_map[col] = field
        
        df = df.rename(columns=rename_map)
        
        # 2. Очистка и Математика
        stats = {"created": 0, "updated": 0, "deactivated": 0, "errors": 0}
        
        # Удаляем строки, где нет Названия (мусор)
        if 'name' in df.columns:
            df = df.dropna(subset=['name'])
        else:
            raise ValueError("У файлі немає колонки з Назвою товару!")

        # --- ОХОТА ЗА АРТИКУЛОМ (SKU) ---
        def extract_sku(row):
            # А. Если есть колонка SKU - берем её
            if 'sku' in row and pd.notnull(row['sku']):
                val = str(row['sku']).replace('.0', '').strip()
                if val: return val
            
            # Б. Ищем 8 цифр в названии
            if 'name' in row:
                match = re.search(r'\b(\d{8})\b', str(row['name']))
                if match:
                    return match.group(1)
            return None

        df['final_sku'] = df.apply(extract_sku, axis=1)
        # Удаляем те, где не нашли артикул
        df = df.dropna(subset=['final_sku'])
        
        # --- КОНВЕРТАЦИЯ ЧИСЕЛ (10,5 -> 10.5) ---
        def clean_float(val):
            if pd.isna(val): return 0.0
            s = str(val).replace(',', '.').replace(' ', '')
            try:
                return float(s)
            except:
                return 0.0

        # Обрабатываем числовые поля
        for col in ['qty_total', 'price', 'total_sum', 'months_inactive']:
            if col in df.columns:
                df[col] = df[col].apply(clean_float)
            else:
                df[col] = 0.0 # Заполняем нулями, если колонки нет

        # --- РАСЧЕТ ЦЕНЫ ---
        # Если цены нет, но есть сумма и количество -> делим
        if 'price' not in rename_map.values():
             # Защита от деления на 0
             df['price'] = df.apply(
                 lambda r: r['total_sum'] / r['qty_total'] if r['qty_total'] > 0 else 0, 
                 axis=1
             )

        # 3. СИНХРОНИЗАЦИЯ С БД
        
        # Получаем все товары из файла (уникальные SKU)
        file_products = df.to_dict('records')
        file_skus = set(df['final_sku'].unique())
        
        # Получаем все товары из БД
        stmt = select(Product)
        result = await self.session.execute(stmt)
        db_products = {p.sku: p for p in result.scalars().all()}
        
        # A. UPDATE & INSERT
        for row in file_products:
            sku = row['final_sku']
            
            name = str(row.get('name', 'No Name'))
            group = str(row.get('group', '')) if row.get('group') else None
            dept = str(row.get('department', '')) if row.get('department') else None
            
            # Конвертируем float 100.0 -> "100" для отдела
            if dept and dept.endswith('.0'): dept = dept[:-2]

            qty = float(row.get('qty_total', 0))
            price = float(row.get('price', 0))
            months = int(row.get('months_inactive', 0))

            if sku in db_products:
                # UPDATE
                prod = db_products[sku]
                prod.name = name
                prod.qty_total = qty
                prod.price = price
                prod.months_inactive = months
                prod.is_active = True # Воскрешаем
                if group: prod.group = group
                if dept: prod.department = dept
                stats['updated'] += 1
            else:
                # INSERT
                new_prod = Product(
                    sku=sku,
                    name=name,
                    qty_total=qty,
                    price=price,
                    months_inactive=months,
                    group=group,
                    department=dept,
                    is_active=True
                )
                self.session.add(new_prod)
                stats['created'] += 1
        
        # B. SOFT DELETE (Те, что пропали из файла)
        # Логика: Если товара нет в файле - значит его нет на остатках.
        # Но мы не удаляем запись, а ставим is_active = False
        for sku, prod in db_products.items():
            if sku not in file_skus and prod.is_active:
                prod.is_active = False
                prod.qty_total = 0 # Обнуляем остаток
                stats['deactivated'] += 1
        
        await self.session.commit()
        return stats

    async def save_mapping_decision(self, header: str, field: str):
        """Сохраняет выбор админа (маппинг)"""
        norm_header = self._normalize_header(header)
        # Проверяем, нет ли уже
        stmt = select(ImportMapping).where(ImportMapping.original_header == norm_header)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.target_field = field
        else:
            self.session.add(ImportMapping(original_header=norm_header, target_field=field))
        await self.session.commit()