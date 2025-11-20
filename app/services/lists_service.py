# app/services/lists_service.py

from __future__ import annotations

from typing import List, Dict, Any, Optional

from sqlalchemy import select, update, func, desc, and_
from sqlalchemy.orm import selectinload

from app.config.settings import Settings
from app.config.departments_map import get_department_name
from app.db.session import AsyncSessionLocal
from app.db.models import UserList, ListItem, Item
from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="lists_service")


# -------------------------
# Відділи (dept)
# -------------------------


async def load_departments(settings: Settings) -> List[Dict[str, Any]]:
    """
    Читає з БД унікальні відділи з таблиці items.
    """
    async with AsyncSessionLocal() as session:
        # Групуємо по dept_code, рахуємо кількість
        stmt = (
            select(Item.dept_code, Item.dept_name, func.count(Item.id).label("count"))
            .where(Item.dept_code.is_not(None), Item.dept_code != "")
            .group_by(Item.dept_code, Item.dept_name)
            .order_by(Item.dept_code)
        )
        result = await session.execute(stmt)
        rows = result.all()

    departments: List[Dict[str, Any]] = []
    for row in rows:
        code = str(row.dept_code)
        # Беремо ім'я з БД, якщо немає - з файлу конфігу
        db_name = str(row.dept_name or "").strip()
        mapped_name = get_department_name(code)
        final_name = db_name or mapped_name or ""

        departments.append(
            {
                "dept_code": code,
                "dept_name": final_name,
                "items_count": int(row.count),
            }
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
    async with AsyncSessionLocal() as session:
        new_list = UserList(
            user_id=user_id,
            dept_code=dept_code,
            mode=mode,
            status="draft"
        )
        session.add(new_list)
        await session.commit()
        # Refresh щоб отримати ID
        await session.refresh(new_list)
        list_id = new_list.id

    log.info(
        "Створено новий список",
        extra={"list_id": list_id, "user_id": user_id, "dept_code": dept_code},
    )
    return list_id


async def load_user_lists_for_user(
    settings: Settings,
    user_id: int,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Повертає останні N списків користувача.
    """
    async with AsyncSessionLocal() as session:
        stmt = (
            select(UserList)
            .where(UserList.user_id == user_id)
            .order_by(desc(UserList.created_at), desc(UserList.id))
            .limit(limit)
        )
        result = await session.execute(stmt)
        lists_orm = result.scalars().all()

    data = []
    for lst in lists_orm:
        code = str(lst.dept_code)
        dept_name = get_department_name(code)
        data.append({
            "id": lst.id,
            "dept_code": code,
            "dept_name": dept_name or "",
            "mode": lst.mode,
            "status": lst.status,
            "created_at": str(lst.created_at),
        })
    return data


async def set_active_list(
    settings: Settings,
    user_id: int,
    list_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Робить вибраний список 'active', інші списки користувача — 'draft'.
    """
    async with AsyncSessionLocal() as session:
        # Перевірка власника
        stmt_get = select(UserList).where(UserList.id == list_id)
        result = await session.execute(stmt_get)
        target_list = result.scalar_one_or_none()

        if not target_list or target_list.user_id != user_id:
            return None

        # Скидаємо всі активні в draft
        await session.execute(
            update(UserList)
            .where(UserList.user_id == user_id, UserList.status == "active")
            .values(status="draft")
        )

        # Ставимо active поточному
        target_list.status = "active"
        target_list.updated_at = func.now()
        
        await session.commit()
        await session.refresh(target_list)

        dept_name = get_department_name(target_list.dept_code)
        return {
            "id": target_list.id,
            "user_id": target_list.user_id,
            "dept_code": target_list.dept_code,
            "dept_name": dept_name or "",
            "mode": target_list.mode,
            "status": target_list.status,
            "created_at": str(target_list.created_at),
        }


async def get_active_list_for_user(
    settings: Settings,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Повертає активний список користувача.
    """
    async with AsyncSessionLocal() as session:
        stmt = (
            select(UserList)
            .where(UserList.user_id == user_id, UserList.status == "active")
            .order_by(desc(UserList.updated_at))
            .limit(1)
        )
        result = await session.execute(stmt)
        lst = result.scalar_one_or_none()

    if not lst:
        return None

    dept_name = get_department_name(lst.dept_code)
    return {
        "id": lst.id,
        "dept_code": lst.dept_code,
        "dept_name": dept_name or "",
        "mode": lst.mode,
        "status": lst.status,
        "created_at": str(lst.created_at),
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
    Додає товар у list_items, фіксуючи snapshot даних.
    """
    async with AsyncSessionLocal() as session:
        # Перевіряємо, чи вже є цей товар у списку
        stmt_check = select(ListItem).where(
            ListItem.list_id == list_id,
            ListItem.item_id == item_id
        )
        existing = (await session.execute(stmt_check)).scalar_one_or_none()
        if existing:
            # Якщо вже є, нічого не робимо (або можна оновити updated_at)
            return

        # Створюємо новий запис
        new_item = ListItem(
            list_id=list_id,
            item_id=item_id,
            
            # Снепшоти
            sku_snapshot=str(item_data.get("sku", "")),
            name_snapshot=str(item_data.get("name", "")),
            dept_snapshot=str(item_data.get("dept_code", "")),
            price_snapshot=item_data.get("price"),
            mt_months_snapshot=item_data.get("mt_months"),
            
            qty=0.0,
            surplus_qty=0.0,
            status="new"
        )
        session.add(new_item)

        # Оновлюємо час редагування списку
        await session.execute(
            update(UserList)
            .where(UserList.id == list_id)
            .values(updated_at=func.now())
        )
        
        await session.commit()


async def update_item_qty(
    settings: Settings,
    list_id: int,
    item_id: int,
    delta: float = 0,
    set_exact: Optional[float] = None,
    is_surplus: bool = False
) -> Dict[str, Any]:
    """
    Змінює кількість товару у списку.
    """
    async with AsyncSessionLocal() as session:
        # Отримуємо ListItem разом з даними про Item (для перевірки залишків)
        stmt = (
            select(ListItem, Item)
            .join(Item, ListItem.item_id == Item.id)
            .where(ListItem.list_id == list_id, ListItem.item_id == item_id)
        )
        result = await session.execute(stmt)
        row = result.first()
        
        if not row:
            return {"status": "error", "msg": "Товар не у списку"}

        list_item, item_obj = row

        # Доступно для збору (фізично в базі)
        available = max(0.0, (item_obj.base_qty or 0.0) - (item_obj.base_reserve or 0.0))

        current_collected = list_item.qty or 0.0
        current_surplus = list_item.surplus_qty or 0.0
        
        new_collected = current_collected
        new_surplus = current_surplus

        if is_surplus:
            # Робота з надлишком
            if set_exact is not None:
                new_surplus = float(set_exact)
            else:
                new_surplus += delta
            if new_surplus < 0: 
                new_surplus = 0.0
        else:
            # Робота з основним збором
            if set_exact is not None:
                target = float(set_exact)
            else:
                target = current_collected + delta
            
            # Обмежуємо основним залишком
            if target > available:
                new_collected = available
                # Можна було б автоматично кидати в надлишок, але поки просто ліміт
            elif target < 0:
                new_collected = 0.0
            else:
                new_collected = target

        # Зберігаємо
        list_item.qty = new_collected
        list_item.surplus_qty = new_surplus
        list_item.updated_at = datetime.now() # Або func.now() в update

        # Також оновимо UserList.updated_at
        await session.execute(
            update(UserList)
            .where(UserList.id == list_id)
            .values(updated_at=func.now())
        )

        await session.commit()

        return {
            "status": "ok",
            "collected": new_collected,
            "surplus": new_surplus,
            "available": available,
            "base_reserve": item_obj.base_reserve
        }