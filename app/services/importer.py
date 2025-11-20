# app/services/importer.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from app.db.base import ItemsRepository
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="import")


@dataclass
class ImportResult:
    """Результат імпорту одного файлу."""

    rows_total: int
    items_processed: int
    added: int
    updated: int
    deactivated: int


# -----------------------------
# Внутрішні утиліти
# -----------------------------


def _detect_engine(path: Path) -> Optional[str]:
    """
    Визначає рекомендований engine для pandas.read_excel за розширенням файлу.

    - .xlsx, .xlsm, .xltx, .xltm -> openpyxl
    - .ods -> odf
    - інакше -> None (pandas сам обере)
    """
    suf = path.suffix.lower()
    if suf in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return "openpyxl"
    if suf == ".ods":
        return "odf"
    return None


# Словник можливих назв колонок (різні мови/варіанти написання)
# ДОДАНО однобуквені заголовки під формат: в, г, а, н, м, к, с
COLUMN_ALIASES: Dict[str, List[str]] = {
    # логічне поле -> можливі частини імені стовпця
    "dept_code": [
        "code",
        "код",
        "отдел",
        "відділ",
        "dept",
        "в",           # коротке позначення "відділ"
    ],
    "dept_name": [
        "dept_name",
        "відділ",
        "отдел",
        "department",
    ],
    "group_name": [
        "fg1_name",
        "группа",
        "група",
        "category",
        "г",           # коротке позначення "група"
    ],
    "articul_name": [
        "articul_name",
        "артикул",
        "артикул ",
        "articul name",
    ],
    "sku": [
        "sku",
        "артикул",
        "код товара",
        "код",
        "item code",
        "а",           # коротке позначення "артикул"
    ],
    "name": [
        "name",
        "назва",
        "наименование",
        "товар",
        "опис",
        "н",           # коротке позначення "назва"
    ],
    "qty": [
        "залишок, к-ть",
        "остаток, к-во",
        "кол-во",
        "количество",
        "qty",
        "quantity",
        "к",           # коротке позначення "кількість"
    ],
    "sum": [
        "залишок, сума",
        "сумма",
        "amount",
        "total",
        "value",
        "с",           # коротке позначення "сума"
    ],
    "mt_months": [
        "міс",
        "месяц",
        "months",
        "months_no_sale",
        "м",           # коротке позначення "місяців без руху"
    ],
    "reserve": [
        "резерв",
        "в резерві",
        "в резерве",
        "reserved",
    ],
    "price": [
        "цена",
        "price",
        "unit price",
    ],
}


def _find_column(columns: Iterable[str], aliases: List[str]) -> Optional[str]:
    """
    Повертає назву стовпця з DataFrame, яка хоч якось збігається
    з одним із alias (по входженню, без регістру), або None.
    """
    cols = list(columns)
    lower_cols = {c: c.lower() for c in cols}

    for alias in aliases:
        alias_l = alias.lower()
        for orig, low in lower_cols.items():
            if alias_l in low:
                return orig
    return None


def _safe_float(value: Any) -> Optional[float]:
    """
    Акуратне перетворення в float з підтримкою європейського роздільника коми.
    Напр. '1,54' -> 1.54.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _split_articul_name(raw: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Розділяє значення типу '70239082 - Назва товару' на (sku, name).
    Спроба виділити перші 8 цифр як артикул, решту як назву.
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None

    # Прагматично: ділимо за першим дефісом
    parts = s.split("-", 1)
    sku = None
    name = None

    if len(parts) == 2:
        left = parts[0].strip()
        right = parts[1].strip()
        # Перше слово зліва вважаємо артикулом, якщо це 8 цифр
        first_token = left.split()[0]
        if first_token.isdigit() and len(first_token) == 8:
            sku = first_token
            name = right or None

    return sku, name or None


# -----------------------------
# Основна логіка імпорту
# -----------------------------


def _detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """
    Пробує знайти відповідність логічних полів (dept_code, qty, sum, ...)
    до реальних назв колонок у DataFrame.

    Поки що робимо це автоматично за COLUMN_ALIASES.
    У майбутньому сюди "прикрутиться" профіль імпорту з БД (import_profiles).
    """
    cols_map: Dict[str, Optional[str]] = {}

    for logical, aliases in COLUMN_ALIASES.items():
        cols_map[logical] = _find_column(df.columns, aliases)

    return cols_map


def _row_to_item_dict(row: pd.Series, cols: Dict[str, Optional[str]]) -> Optional[Dict[str, Any]]:
    """
    Конвертує один рядок DataFrame у dict у форматі, який очікує
    ItemsRepository.upsert_from_import (sirі дані до нормалізації).
    """
    # Відділ / група
    dept_code = row.get(cols.get("dept_code")) if cols.get("dept_code") else None
    dept_name = row.get(cols.get("dept_name")) if cols.get("dept_name") else None
    group_name = row.get(cols.get("group_name")) if cols.get("group_name") else None

    # Артикул + назва
    sku = None
    name = None

    if cols.get("sku"):
        raw_sku = row.get(cols["sku"])
        if raw_sku is not None:
            s = str(raw_sku).strip()
            if s:
                sku = s

    if cols.get("name"):
        raw_name = row.get(cols["name"])
        if raw_name is not None:
            n = str(raw_name).strip()
            if n:
                name = n

    # Якщо є articul_name (типу "70239082 - Назва") — намагаємось розділити
    if cols.get("articul_name"):
        raw_an = row.get(cols["articul_name"])
        sku2, name2 = _split_articul_name(raw_an)
        if sku is None and sku2 is not None:
            sku = sku2
        if name is None and name2 is not None:
            name = name2

    if not sku:
        # Без артикулу рядок нам нецікавий
        return None

    # Кількість і сума
    qty_val = row.get(cols.get("qty")) if cols.get("qty") else None
    sum_val = row.get(cols.get("sum")) if cols.get("sum") else None
    qty = _safe_float(qty_val) or 0.0
    total_sum = _safe_float(sum_val) or 0.0

    # МТ, резерв, ціна
    mt_raw = row.get(cols.get("mt_months")) if cols.get("mt_months") else None
    mt_months = _safe_float(mt_raw)

    reserve_raw = row.get(cols.get("reserve")) if cols.get("reserve") else None
    reserve = _safe_float(reserve_raw) or 0.0

    price_raw = row.get(cols.get("price")) if cols.get("price") else None
    price = _safe_float(price_raw)

    data: Dict[str, Any] = {
        "sku": sku,
        "dept_code": str(dept_code).strip() if dept_code is not None else "",
        "dept_name": str(dept_name).strip() if dept_name is not None else None,
        "group_name": str(group_name).strip() if group_name is not None else None,
        "name": name or "",
        "unit": "шт",  # поки що дефолт, можна буде брати з окремої колонки
        "mt_months": mt_months,
        "qty": qty,
        "sum": total_sum,
        "reserve": reserve,
        "price": price,
    }
    return data


def _read_table(path: Path) -> pd.DataFrame:
    """
    Зчитує Excel/ODS у DataFrame за допомогою pandas.read_excel.

    Для .xlsx → engine='openpyxl'
    Для .ods  → engine='odf'
    Інакше pandas сам обирає engine.
    """
    engine = _detect_engine(path)
    read_kwargs: Dict[str, Any] = {
        "dtype": object,  # читаємо як object, щоб далі самі конвертувати
    }
    if engine:
        read_kwargs["engine"] = engine

    log.info(f"Читаємо таблицю з файлу: {path} (engine={engine or 'auto'})")
    df = pd.read_excel(path, **read_kwargs)
    log.info(f"Зчитано рядків: {len(df)}; колонок: {list(df.columns)}")
    return df


# -----------------------------
# Публічний API сервісу імпорту
# -----------------------------


async def import_items_from_file(
    file_path: Path,
    items_repo: ItemsRepository,
    *,
    deactivate_missing: bool = True,
) -> ImportResult:
    """
    Повний цикл імпорту:
    - читає файл (Excel/ODS) у DataFrame;
    - за назвою колонок пробує знайти відділ/артикул/назву/к-ть/суму/МТ/резерв;
    - конвертує рядки в список dict'ів;
    - передає їх у items_repo.upsert_from_import;
    - повертає короткий результат.

    Формат, який очікує items_repo.upsert_from_import:
    {
        "sku": str,
        "dept_code": str,
        "dept_name": Optional[str],
        "group_name": Optional[str],
        "name": str,
        "unit": str,
        "mt_months": Optional[float],
        "qty": float,
        "sum": float,
        "reserve": float,
        "price": Optional[float],
    }
    """
    file_path = file_path.expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Файл для імпорту не знайдено: {file_path}")

    # Зчитуємо таблицю синхронно (для великих файлів можна винести в executor)
    df = _read_table(file_path)
    rows_total = len(df)

    if rows_total == 0:
        log.warning("Файл порожній, імпортувати нічого")
        return ImportResult(
            rows_total=0,
            items_processed=0,
            added=0,
            updated=0,
            deactivated=0,
        )

    cols = _detect_columns(df)
    log.info(f"Авто-мапінг колонок: {cols}")

    raw_items: List[Dict[str, Any]] = []
    skipped_rows = 0

    for idx, row in df.iterrows():
        item_dict = _row_to_item_dict(row, cols)
        if not item_dict:
            skipped_rows += 1
            continue
        raw_items.append(item_dict)

    log.info(
        "Після попередньої обробки: рядків=%s, товарів до імпорту=%s, пропущено (без sku)=%s",
        rows_total,
        len(raw_items),
        skipped_rows,
    )

    if not raw_items:
        return ImportResult(
            rows_total=rows_total,
            items_processed=0,
            added=0,
            updated=0,
            deactivated=0,
        )

    stats = await items_repo.upsert_from_import(raw_items, deactivate_missing=deactivate_missing)

    return ImportResult(
        rows_total=rows_total,
        items_processed=len(raw_items),
        added=stats.get("added", 0),
        updated=stats.get("updated", 0),
        deactivated=stats.get("deactivated", 0),
    )
