# app/services/importer.py

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.session import AsyncSessionLocal
from app.db.models import Item
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="import")


@dataclass
class ImportResult:
    """Результат імпорту."""
    rows_total: int
    items_processed: int
    added: int
    updated: int
    deactivated: int


# -----------------------------
# Словник синонімів
# -----------------------------

COLUMN_ALIASES: Dict[str, List[str]] = {
    "sku": [
        "sku", "артикул", "код товара", "код", "item code", "а", "articul"
    ],
    "name": [
        "name", "назва", "наименование", "товар", "опис", "н", "name_ua"
    ],
    "dept_code": [
        "dept", "code", "код відділу", "отдел", "відділ", "в", "dept_code"
    ],
    "dept_name": [
        "dept_name", "назва відділу", "department"
    ],
    "qty": [
        "qty", "к-ть", "кількість", "кол-во", "залишок", "к", "quantity", "залишок, к-ть"
    ],
    "sum": [
        "sum", "сума", "сумма", "amount", "total", "с", "залишок, сума"
    ],
    "mt_months": [
        "mt", "months", "міс", "без руху", "м", "міс без продажу", "mt_months"
    ],
    "reserve": [
        "reserve", "резерв", "в резерві", "reserved"
    ],
    # Комбіновані колонки
    "articul_name": [
        "articul_name", "артикул_назва", "товар (арт)"
    ]
}


# -----------------------------
# Допоміжні функції (Парсинг)
# -----------------------------

def _safe_float(value: Any) -> float:
    """Конвертує рядок/число у float, прибираючи пробіли (1 000,00)."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    
    s = str(value).strip()
    if not s:
        return 0.0
    
    # Прибираємо нерозривні пробіли та звичайні пробіли, кому на крапку
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _clean_sku(value: Any) -> Optional[str]:
    """Очищає артикул (тільки цифри, має бути 8 символів)."""
    if value is None:
        return None
    s = str(value).strip()
    # Якщо у комірці "70117244 - Назва", пробуємо спліт
    match = re.match(r'^(\d{8})[\s\-\.]+', s)
    if match:
        return match.group(1)
    
    # Якщо просто цифри
    digits = "".join(filter(str.isdigit, s))
    if len(digits) == 8:
        return digits
    return None


def _split_sku_name(row: pd.Series, cols: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Намагається дістати SKU та Name з рядка, враховуючи можливі склеєні колонки.
    """
    sku = None
    name = None

    # 1. Спробуємо явні колонки
    if cols.get("sku"):
        raw_sku = row[cols["sku"]]
        sku = _clean_sku(raw_sku)

    if cols.get("name"):
        name = str(row[cols["name"]]).strip()

    # 2. Якщо SKU немає або є спец-колонка "articul_name"
    if not sku:
        # Перевіримо, чи не сховався SKU в колонці Name (часто буває)
        if name:
            potential_sku = _clean_sku(name)
            if potential_sku:
                sku = potential_sku
                # Можна спробувати обрізати SKU з назви, але не обов'язково

        # Перевіримо колонку articul_name
        if cols.get("articul_name"):
            raw_an = str(row[cols["articul_name"]])
            potential_sku = _clean_sku(raw_an)
            if potential_sku:
                sku = potential_sku
                if not name:
                     # Пробуємо взяти все після артикулу як назву
                     parts = re.split(r'[\s\-\.]+', raw_an, maxsplit=1)
                     if len(parts) > 1:
                         name = parts[1].strip()

    return sku, name


def _find_header_row(df_raw: pd.DataFrame) -> int:
    """
    Шукає індекс рядка, який найбільше схожий на заголовок.
    Сканує перші 20 рядків.
    """
    best_idx = 0
    max_matches = 0

    # Ключові слова, які точно мають бути в заголовку
    keywords = ["sku", "артикул", "код", "назва", "name", "qty", "к-ть", "в", "г", "а", "н"]

    for i in range(min(20, len(df_raw))):
        row_values = df_raw.iloc[i].astype(str).str.lower().tolist()
        matches = sum(1 for val in row_values for kw in keywords if kw == val or kw in val)
        
        if matches > max_matches:
            max_matches = matches
            best_idx = i
            
    return best_idx


# -----------------------------
# Основна логіка
# -----------------------------

async def import_items_from_file(
    file_path: Path,
    deactivate_missing: bool = True,
) -> ImportResult:
    """
    Головна функція імпорту.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # 1. Читаємо файл (Pandas)
    ext = file_path.suffix.lower()
    
    try:
        if ext == ".csv":
            # Читаємо "сиро" спочатку, щоб знайти заголовок
            df_raw = pd.read_csv(file_path, header=None, dtype=str)
        elif ext in [".xls", ".xlsx"]:
            df_raw = pd.read_excel(file_path, header=None, dtype=str)
        elif ext == ".ods":
            df_raw = pd.read_excel(file_path, engine="odf", header=None, dtype=str)
        else:
            raise ValueError(f"Unsupported format: {ext}")
    except Exception as e:
        log.error(f"Failed to read file: {e}")
        return ImportResult(0,0,0,0,0)

    # 2. Шукаємо заголовок
    header_idx = _find_header_row(df_raw)
    
    # Перечитуємо з правильним заголовком
    if ext == ".csv":
        df = pd.read_csv(file_path, header=header_idx, dtype=str)
    elif ext in [".xls", ".xlsx"]:
        df = pd.read_excel(file_path, header=header_idx, dtype=str)
    else:
        df = pd.read_excel(file_path, engine="odf", header=header_idx, dtype=str)

    rows_total = len(df)
    log.info(f"Loaded {rows_total} rows. Header found at index {header_idx}")

    # 3. Мапимо колонки
    cols_map = {}
    df.columns = df.columns.str.strip().str.lower() # нормалізуємо заголовки файлу
    
    for logical_name, aliases in COLUMN_ALIASES.items():
        for col_name in df.columns:
            if col_name in aliases: # точне співпадіння
                cols_map[logical_name] = col_name
                break
            # часткове співпадіння (обережно)
            for alias in aliases:
                 if alias == col_name: 
                     cols_map[logical_name] = col_name
                     break
    
    log.info(f"Columns mapped: {cols_map}")

    if "sku" not in cols_map and "articul_name" not in cols_map and "a" not in df.columns:
        # Критично, якщо не знайшли артикул
        # Спробуємо знайти колонку 'а' (кирилиця або латиниця) вручну, якщо автомапінг не спрацював
        pass 

    # 4. Парсимо рядки
    items_to_upsert = []
    valid_skus = set()

    for _, row in df.iterrows():
        sku, name = _split_sku_name(row, cols_map)
        
        if not sku:
            continue

        valid_skus.add(sku)

        # Числа
        qty = _safe_float(row.get(cols_map.get("qty")))
        total_sum = _safe_float(row.get(cols_map.get("sum")))
        reserve = _safe_float(row.get(cols_map.get("reserve")))
        mt = _safe_float(row.get(cols_map.get("mt_months")))

        # Ціна (розрахунок)
        price = 0.0
        if qty > 0:
            price = round(total_sum / qty, 2)
        
        # Відділ
        dept_code = str(row.get(cols_map.get("dept_code"), "")).split(".")[0].strip() # 10.0 -> 10
        dept_name = str(row.get(cols_map.get("dept_name"), "")).strip()
        
        # Якщо відділ порожній, ставимо заглушку (можна покращити)
        if not dept_code:
            dept_code = "UNKNOWN"

        items_to_upsert.append({
            "sku": sku,
            "name": name or "Без назви",
            "dept_code": dept_code,
            "dept_name": dept_name if dept_name else None,
            "group_name": None, # Поки не парсимо
            "price": price,
            "base_qty": qty,
            "base_reserve": reserve,
            "mt_months": mt,
            # "updated_at": datetime.now() # SQLAlchemy поставить саме
        })

    # 5. Запис у БД (Upsert)
    async with AsyncSessionLocal() as session:
        added = 0
        updated = 0
        
        # Для SQLite upsert робиться через on_conflict_do_update
        # Для Postgres так само, синтаксис майже ідентичний в SQLAlchemy 2.0
        
        for item_data in items_to_upsert:
            stmt = sqlite_insert(Item).values(**item_data)
            
            # Що оновлюємо при конфлікті
            do_update_stmt = stmt.on_conflict_do_update(
                index_elements=['sku'],
                set_={
                    "dept_code": stmt.excluded.dept_code,
                    "dept_name": stmt.excluded.dept_name,
                    "name": stmt.excluded.name,
                    "price": stmt.excluded.price,
                    "base_qty": stmt.excluded.base_qty,
                    "base_reserve": stmt.excluded.base_reserve,
                    "mt_months": stmt.excluded.mt_months,
                    "updated_at": list(stmt.excluded.updated_at)[0] if hasattr(stmt.excluded, 'updated_at') else None 
                    # SQLAlchemy сам розбереться з часом
                }
            )
            await session.execute(do_update_stmt)
            # (Точний підрахунок added/updated складний при масовому insert, пропустимо для швидкості)

        # 6. Деактивація відсутніх
        deactivated = 0
        if deactivate_missing and valid_skus:
            # Ставимо qty = 0 для тих, кого немає у файлі
            deact_stmt = (
                update(Item)
                .where(Item.sku.not_in(valid_skus))
                .values(base_qty=0, base_reserve=0, mt_months=0)
            )
            result = await session.execute(deact_stmt)
            deactivated = result.rowcount

        await session.commit()

    return ImportResult(
        rows_total=rows_total,
        items_processed=len(items_to_upsert),
        added=len(items_to_upsert), # Приблизно
        updated=0,
        deactivated=deactivated
    )