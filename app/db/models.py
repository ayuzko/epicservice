# app/db/models.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime, BigInteger, Boolean
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="user")  # user / admin
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    dept_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    dept_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    group_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str] = mapped_column(String, default="шт")
    
    price: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Остатки из базы (импорт)
    base_qty: Mapped[float] = mapped_column(Float, default=0.0)
    base_reserve: Mapped[float] = mapped_column(Float, default=0.0)
    
    mt_months: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

class UserList(Base):
    __tablename__ = "user_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True) # Telegram ID
    dept_code: Mapped[str] = mapped_column(String, nullable=False)
    
    mode: Mapped[str] = mapped_column(String, default="manual") # manual / carousel
    status: Mapped[str] = mapped_column(String, default="draft") # draft / active / saved
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Связь с позициями
    items: Mapped[List["ListItem"]] = relationship(
        "ListItem", back_populates="list_obj", cascade="all, delete-orphan"
    )

class ListItem(Base):
    __tablename__ = "list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("user_lists.id"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)

    # Фиксация данных на момент добавления (Snapshot)
    sku_snapshot: Mapped[str] = mapped_column(String)
    name_snapshot: Mapped[str] = mapped_column(String)
    dept_snapshot: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    price_snapshot: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mt_months_snapshot: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Сколько собрали
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    surplus_qty: Mapped[float] = mapped_column(Float, default=0.0) # Излишек

    status: Mapped[str] = mapped_column(String, default="new") # new / done / skipped
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    list_obj: Mapped["UserList"] = relationship("UserList", back_populates="items")
    item: Mapped["Item"] = relationship("Item")