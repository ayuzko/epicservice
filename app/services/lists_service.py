# app/services/lists_service.py

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional

import aiosqlite

from app.config.settings import Settings
from app.config.departments_map import get_department_name
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="lists_service")


# -------------------------
# Базові утиліти
# -------------------------


def _get_sqlite_path(settings: Settings) -> Path:
    """
    Дістає шлях до файлу SQLite з DB_URL виду 'sqlite:///data/bot.db'.
    """
    url = settings.DB_URL
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Наразі підтримується лише SQLite з DB_URL=sqlite:///...")
    path_str = url.replace("sqlite:///", "", 1)
    return Path(path_str).expanduser().resolve()


# -------------------------
# Відділи (dept)
# -------------------------


async def load_departments(settings: Settings) -> List[Dict[str, Any]]:
    """
    Читає з БД унікальні відділи з таблиці items.

    Якщо dept_name порожнє – підставляємо назву з departments.json.
    """
    db_path = _get_sqlite_path(settings)
    log.info("Завантажуємо відділи з SQLite", extra={"db_path": str(db_path)})

    query = """
    SELECT
        dept_code,
        COALESCE(dept_name, '') AS dept_name,
        COUNT(*) AS items_count
    FROM items
    WHERE dept_code IS NOT NULL AND TRIM(dept_code) <> ''
    GROUP BY dept_code, dept_name
    ORDER BY dept_code
    """

    departments: List[Dict[str, Any]] = []

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query) as cur:
            rows = await cur.fetchall()

    for row in rows:
        code = str(row["dept_code"])
        db_name = str(row["dept_name"] or "").strip()
        mapped_name = get_department_name(code)
        final_name = db_name or mapped_name or ""

        departments.append(
            {
                "dept_code": code,
                "dept_name": final_name,
                "items_count": int(row["items_count"]),
            }
        )

    log.info(
        "Знайдено відділів: %s",
        len(departments),
        extra={"departments": [f'{d["dept_code"]}={d["dept_name"]}' for d in departments]},
    )
    return departments


# -------------------------
# Операції з user_lists
# -------------------------


async def create_user_list(
    settings: Settings,
    user_id: int,
    dept_code: str,
    mode: str,
) -> int:
    """
    Створює запис списку в user_lists.
    """
    db_path = _get_sqlite_path(settings)

    insert_sql = """
    INSERT INTO user_lists (user_id, dept_code, mode, status)
    VALUES (?, ?, ?, 'draft');
    """

    async with aiosqlite.connect(str(db_path)) as conn:
        cur = await conn.execute(insert_sql, (user_id, dept_code, mode))
        await conn.commit()
        list_id = cur.lastrowid or 0

    log.info(
        "Створено новий список",
        extra={"list_id": list_id, "user_id": user_id, "dept_code": dept_code, "mode": mode},
    )
    return int(list_id)


async def load_user_lists_for_user(
    settings: Settings,
    user_id: int,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Повертає останні N списків користувача.
    """
    db_path = _get_sqlite_path(settings)

    query = """
    SELECT id, dept_code, mode, status, created_at
    FROM user_lists
    WHERE user_id = ?
    ORDER BY datetime(created_at) DESC, id DESC
    LIMIT ?
    """

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query, (user_id, limit)) as cur:
            rows = await cur.fetchall()

    lists: List[Dict[str, Any]] = []
    for row in rows:
        code = str(row["dept_code"])
        dept_name = get_department_name(code)
        lists.append(
            {
                "id": int(row["id"]),
                "dept_code": code,
                "dept_name": dept_name or "",
                "mode": str(row["mode"]),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
            }
        )

    log.info(
        "Завантажено списків користувача",
        extra={"user_id": user_id, "count": len(lists)},
    )
    return lists


async def set_active_list(
    settings: Settings,
    user_id: int,
    list_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Робить вибраний список 'active', інші списки користувача — 'draft'.
    """
    db_path = _get_sqlite_path(settings)

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute(
            "SELECT id, user_id, dept_code, mode, status, created_at "
            "FROM user_lists WHERE id = ?",
            (list_id,),
        )
        row = await cur.fetchone()
        if row is None or int(row["user_id"]) != user_id:
            return None

        await conn.execute(
            "UPDATE user_lists SET status = 'draft' WHERE user_id = ?",
            (user_id,),
        )
        await conn.execute(
            "UPDATE user_lists SET status = 'active', updated_at = datetime('now') WHERE id = ?",
            (list_id,),
        )
        await conn.commit()

        code = str(row["dept_code"])
        dept_name = get_department_name(code)

        return {
            "id": int(row["id"]),
            "user_id": int(row["user_id"]),
            "dept_code": code,
            "dept_name": dept_name or "",
            "mode": str(row["mode"]),
            "status": "active",
            "created_at": str(row["created_at"]),
        }


async def get_active_list_for_user(
    settings: Settings,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Повертає активний список користувача (status='active') або None.
    """
    db_path = _get_sqlite_path(settings)

    query = """
    SELECT id, dept_code, mode, status, created_at
    FROM user_lists
    WHERE user_id = ? AND status = 'active'
    ORDER BY datetime(updated_at) DESC, id DESC
    LIMIT 1
    """

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(query, (user_id,))
        row = await cur.fetchone()

    if row is None:
        return None

    code = str(row["dept_code"])
    dept_name = get_department_name(code)
    return {
        "id": int(row["id"]),
        "dept_code": code,
        "dept_name": dept_name or "",
        "mode": str(row["mode"]),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
    }


# -------------------------
# Елементи списку (list_items)
# -------------------------


async def add_item_to_list(
    settings: Settings,
    list_id: int,
    item_id: int,
    item_data: Dict[str, Any],
) -> None:
    """
    Додає товар у list_items, фіксуючи snapshot даних (ціна, відділ, назва, МТ).
    """
    db_path = _get_sqlite_path(settings)

    async with aiosqlite.connect(str(db_path)) as conn:
        # Вставляємо повний набір полів відповідно до schema.sql
        insert_sql = """
        INSERT INTO list_items (
            list_id, item_id, sku,
            sku_snapshot, name_snapshot, dept_snapshot,
            price_snapshot, mt_months_snapshot,
            qty, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'new');
        """

        # Витягуємо дані з безпечними дефолтами
        sku = str(item_data.get("sku", ""))
        name = str(item_data.get("name", ""))
        dept = str(item_data.get("dept_code", ""))
        price = item_data.get("price")
        mt_months = item_data.get("mt_months")

        await conn.execute(insert_sql, (
            list_id,
            item_id,
            sku,
            sku,          # sku_snapshot
            name,         # name_snapshot
            dept,         # dept_snapshot
            price,        # price_snapshot
            mt_months     # mt_months_snapshot
        ))
        
        await conn.execute(
            "UPDATE user_lists SET updated_at = datetime('now') WHERE id = ?",
            (list_id,),
        )
        await conn.commit()