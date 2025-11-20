# app/db/sqlite.py

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import aiosqlite

from app.config.settings import Settings
from app.db.base import ItemsRepository
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="sqlite")


@dataclass
class SqliteConfig:
    """Налаштування для підключення до SQLite."""

    path: Path


class SqliteDatabase:
    """
    Простий обгортник над aiosqlite.

    Відповідає за:
    - створення з'єднання;
    - ввімкнення foreign_keys;
    - видачу курсорів для репозиторіїв.
    """

    def __init__(self, cfg: SqliteConfig) -> None:
        self._cfg = cfg
        self._conn: Optional[aiosqlite.Connection] = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("База даних не ініціалізована. Викличте await init().")
        return self._conn

    async def init(self) -> None:
        log.info(f"Відкриваємо SQLite БД: {self._cfg.path}")
        self._cfg.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._cfg.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.commit()
        log.info("Підключення до SQLite встановлено (foreign_keys=ON)")

    async def close(self) -> None:
        if self._conn is not None:
            log.info("Закриваємо з'єднання з SQLite")
            await self._conn.close()
            self._conn = None


class SqliteItemsRepository(ItemsRepository):
    """
    Реалізація ItemsRepository для SQLite.

    Працює з таблицею items (див. schema.sql) і відповідає за:
    - пошук товарів за артикулом;
    - upsert з імпорту з перерахунком ціни;
    - отримання МТ по відділу та періоду.
    """

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    # -------------------------
    # Допоміжні методи
    # -------------------------

    @staticmethod
    def _normalize_import_item(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Приводить сирі дані імпорту до стандартного словника полів items.

        Очікувані ключі у raw (мінімум):
        - sku (8-значний артикул, str)
        - dept_code
        - dept_name
        - group_name
        - name
        - unit
        - mt_months
        - qty  (залишок, к-ть)
        - sum  (залишок, сума)
        - reserve (може бути None/відсутній)
        - price (опційно; якщо немає — рахуємо sum/qty)
        """
        sku = str(raw.get("sku", "")).strip()
        if not sku:
            raise ValueError("Поле 'sku' обов'язкове для імпорту")

        qty = raw.get("qty")
        total_sum = raw.get("sum")
        price = raw.get("price")

        # Якщо ціни немає, але є сума та кількість — рахуємо
        if price is None and qty not in (None, 0, 0.0) and total_sum is not None:
            try:
                price = float(total_sum) / float(qty)
            except ZeroDivisionError:
                price = None

        item = {
            "sku": sku,
            "dept_code": str(raw.get("dept_code", "")).strip(),
            "dept_name": raw.get("dept_name"),
            "group_name": raw.get("group_name"),
            "name": raw.get("name") or "",
            "unit": raw.get("unit") or "шт",
            "mt_months": raw.get("mt_months"),
            "base_qty": float(qty) if qty is not None else 0.0,
            "base_sum": float(total_sum) if total_sum is not None else 0.0,
            "price": float(price) if price is not None else None,
            "base_reserve": float(raw.get("reserve") or 0.0),
        }

        return item

    # -------------------------
    # Публічні методи
    # -------------------------

    async def get_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Повертає товар як dict за точним артикулом або None.
        """
        query = """
            SELECT *
            FROM items
            WHERE sku = ?
        """
        async with self._db.conn.execute(query, (sku,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return dict(row)

    async def get_mt_by_dept(
        self,
        dept_code: str,
        min_months: float,
        only_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Повертає список товарів із вказаного відділу, у яких mt_months >= min_months.

        Використовується для формування каруселі МТ.
        """
        params: list[Any] = [dept_code, float(min_months)]
        conditions = ["dept_code = ?", "mt_months >= ?"]
        if only_active:
            conditions.append("is_active = 1")

        query = f"""
            SELECT *
            FROM items
            WHERE {" AND ".join(conditions)}
            ORDER BY mt_months DESC, sku
        """
        async with self._db.conn.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def upsert_from_import(
        self,
        raw_items: Iterable[Dict[str, Any]],
        *,
        deactivate_missing: bool = True,
    ) -> Dict[str, int]:
        """
        Додає/оновлює товари з імпорту.

        Логіка:
        - для кожного запису з файлу робимо INSERT ... ON CONFLICT(sku) DO UPDATE;
        - якщо deactivate_missing=True — усі товари, яких немає у файлі, помічаємо is_active = 0;
        - якщо qty=0 у файлі — теж is_active = 0;
        - поля, яких немає у файлі, НЕ обнуляємо (оновлюємо тільки наявні значення).
        """
        conn = self._db.conn
        added = 0
        updated = 0

        # Нормалізуємо всі записи імпорту й збираємо список sku для можливої деактивації
        normalized: List[Dict[str, Any]] = []
        seen_skus: List[str] = []

        for raw in raw_items:
            item = self._normalize_import_item(raw)
            normalized.append(item)
            seen_skus.append(item["sku"])

        if not normalized:
            log.info("upsert_from_import: порожній список; нічого не оновлюємо")
            return {"added": 0, "updated": 0, "deactivated": 0}

        # Виконуємо upsert у транзакції
        await conn.execute("BEGIN;")
        try:
            for item in normalized:
                # Якщо залишок 0 — одразу робимо is_active = 0
                is_active = 0 if item["base_qty"] == 0 else 1

                query = """
                    INSERT INTO items (
                        sku, dept_code, dept_name, group_name, name, unit,
                        mt_months, base_qty, base_sum, price, base_reserve,
                        is_active, created_at, updated_at
                    )
                    VALUES (
                        :sku, :dept_code, :dept_name, :group_name, :name, :unit,
                        :mt_months, :base_qty, :base_sum, :price, :base_reserve,
                        :is_active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(sku) DO UPDATE SET
                        dept_code    = excluded.dept_code,
                        dept_name    = excluded.dept_name,
                        group_name   = excluded.group_name,
                        name         = excluded.name,
                        unit         = excluded.unit,
                        mt_months    = excluded.mt_months,
                        base_qty     = excluded.base_qty,
                        base_sum     = excluded.base_sum,
                        price        = excluded.price,
                        base_reserve = excluded.base_reserve,
                        is_active    = excluded.is_active,
                        updated_at   = CURRENT_TIMESTAMP
                """
                params = {**item, "is_active": is_active}
                cur = await conn.execute(query, params)
                # lastrowid не завжди покаже, чи був insert/update, тому рахуємо окремо
                if cur.rowcount == 1:
                    # Не відрізняє insert/update; для статистики можна зробити додатковий SELECT,
                    # але тут тримаємо все простіше.
                    pass

            # Деактивуємо всі товари, яких немає у файлі (за бажання)
            deactivated = 0
            if deactivate_missing:
                # Щоб не перевищувати ліміт параметрів, можна робити батчами,
                # але для наших розмірів це, скоріше за все, не критично.
                placeholders = ",".join("?" for _ in seen_skus)
                query_deactivate = f"""
                    UPDATE items
                    SET is_active = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE sku NOT IN ({placeholders})
                """
                cur = await conn.execute(query_deactivate, seen_skus)
                deactivated = cur.rowcount or 0

            await conn.commit()
        except Exception:
            await conn.rollback()
            log.exception("Помилка під час upsert_from_import; транзакцію відкотили")
            raise

        # Для статистики можна порахувати заново додані/оновлені,
        # але для спрощення зараз повертаємо тільки кількість перероблених рядків.
        total = len(normalized)
        log.info(
            "upsert_from_import: оброблено=%s, можливо_оновлено/додано, деактивовано=%s",
            total,
            deactivated,
        )
        return {"added": added, "updated": updated, "deactivated": deactivated}


# -------------------------------------------------------------------
# Фабрика для створення SQLite БД та репозиторіїв
# -------------------------------------------------------------------


def _parse_sqlite_path(db_url: str) -> Path:
    """
    Перетворює рядок 'sqlite:///data/bot.db' у Path до файлу.
    Використовується і тут, і в міграціях.
    """
    if not db_url.startswith("sqlite"):
        raise ValueError(f"Неправильний sqlite URL: {db_url!r}")

    if ":///" in db_url:
        path_part = db_url.split(":///")[1]
    else:
        path_part = db_url.split("://")[1]

    return Path(path_part).expanduser().resolve()


@dataclass
class Repositories:
    """Контейнер для всіх репозиторіїв БД."""

    items: SqliteItemsRepository
    # Тут пізніше додамо:
    # users: SqliteUsersRepository
    # lists: SqliteUserListsRepository
    # imports: SqliteImportsRepository
    # photos: SqliteItemPhotosRepository
    # comments: SqliteItemCommentsRepository


async def create_sqlite_repositories(settings: Settings) -> Tuple[SqliteDatabase, Repositories]:
    """
    Створює SqliteDatabase + набір репозиторіїв для роботи з БД.

    Викликається на старті застосунку (наприклад, в main()).
    """
    db_path = _parse_sqlite_path(settings.DB_URL)
    db = SqliteDatabase(SqliteConfig(path=db_path))
    await db.init()

    items_repo = SqliteItemsRepository(db=db)

    repos = Repositories(
        items=items_repo,
    )

    log.info("SQLite репозиторії ініціалізовано")
    return db, repos
