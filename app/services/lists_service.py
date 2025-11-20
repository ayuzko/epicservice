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
# Структура таблиць списків
# -------------------------


async def ensure_lists_tables(settings: Settings) -> None:
    """
    Гарантує існування таблиць user_lists та list_items
    і, за потреби, додає відсутню колонку sku в list_items.
    """
    db_path = _get_sqlite_path(settings)

    create_lists_sql = """
    CREATE TABLE IF NOT EXISTS user_lists (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        dept_code   TEXT    NOT NULL,
        mode        TEXT    NOT NULL,
        status      TEXT    NOT NULL DEFAULT 'draft',
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """

    # Базова нова схема list_items: list_id + item_id + sku
    create_items_sql = """
    CREATE TABLE IF NOT EXISTS list_items (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        list_id         INTEGER NOT NULL,
        item_id         INTEGER NOT NULL,
        sku             TEXT    NOT NULL,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (list_id) REFERENCES user_lists(id) ON DELETE CASCADE,
        FOREIGN KEY (item_id) REFERENCES items(id)      ON DELETE CASCADE
    );
    """

    async with aiosqlite.connect(str(db_path)) as conn:
        await conn.execute(create_lists_sql)
        await conn.execute(create_items_sql)

        # Перевіряємо колонки list_items (на випадок старої схеми)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("PRAGMA table_info(list_items);")
        rows = await cur.fetchall()
        col_names = {str(row["name"]) for row in rows}

        # Якщо sku нема – додаємо її
        if "sku" not in col_names:
            log.info("Додаємо колонку sku у list_items через ALTER TABLE")
            await conn.execute("ALTER TABLE list_items ADD COLUMN sku TEXT NOT NULL DEFAULT '';")

        await conn.commit()


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
    await ensure_lists_tables(settings)
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
    await ensure_lists_tables(settings)
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
    await ensure_lists_tables(settings)
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
    await ensure_lists_tables(settings)
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
    sku: str,
    name: str,
) -> None:
    """
    Додає товар у list_items, заповнюючи item_id і sku.

    Якщо в існуючій БД є старі NOT NULL‑колонки типу
    sku_snapshot / name_snapshot, також заповнюємо їх.
    """
    await ensure_lists_tables(settings)
    db_path = _get_sqlite_path(settings)

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row

        # Дізнаємось, які саме колонки є в list_items
        cur = await conn.execute("PRAGMA table_info(list_items);")
        rows = await cur.fetchall()
        col_names = {str(row["name"]) for row in rows}

        # Конструюємо INSERT динамічно
        columns = ["list_id", "item_id", "sku"]
        values = [list_id, item_id, sku]

        if "sku_snapshot" in col_names:
            columns.append("sku_snapshot")
            values.append(sku)

        if "name_snapshot" in col_names:
            columns.append("name_snapshot")
            values.append(name or "")

        cols_sql = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)

        insert_sql = f"INSERT INTO list_items ({cols_sql}) VALUES ({placeholders});"

        await conn.execute(insert_sql, values)
        await conn.execute(
            "UPDATE user_lists SET updated_at = datetime('now') WHERE id = ?",
            (list_id,),
        )
        await conn.commit()
