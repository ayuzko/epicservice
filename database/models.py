from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, String, Boolean, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# --- БАЗОВЫЙ КЛАСС ---
class Base(DeclarativeBase):
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# --- 1. КОРИСТУВАЧІ ---
class User(Base):
    __tablename__ = 'users'

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, unique=True, index=True)
    fullname: Mapped[str] = mapped_column(String, nullable=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default='pending') 
    
    lists = relationship("ShoppingList", back_populates="user")
    photos = relationship("ProductPhoto", back_populates="author")

# --- 2. СЛОВНИК ІМПОРТУ ---
class ImportMapping(Base):
    __tablename__ = 'import_mappings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_header: Mapped[str] = mapped_column(String, unique=True, index=True)
    target_field: Mapped[str] = mapped_column(String)

# --- 3. ТОВАРИ ---
class Product(Base):
    __tablename__ = 'products'

    sku: Mapped[str] = mapped_column(String(50), primary_key=True, index=True) 
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    group: Mapped[str] = mapped_column(String, nullable=True)
    department: Mapped[str] = mapped_column(String, nullable=True, index=True)
    
    qty_total: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    months_inactive: Mapped[int] = mapped_column(Integer, default=0) # Тот самый параметр фильтра
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    photos = relationship("ProductPhoto", back_populates="product")

# --- 4. СПИСКИ ЗБОРУ ---
class ShoppingList(Base):
    __tablename__ = 'shopping_lists'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'))
    status: Mapped[str] = mapped_column(String, default='active', index=True)
    department_lock: Mapped[str] = mapped_column(String, nullable=True)
    total_items_count: Mapped[int] = mapped_column(Integer, default=0)
    
    user = relationship("User", back_populates="lists")
    items = relationship("CartItem", back_populates="shopping_list", cascade="all, delete-orphan")

# --- 5. ПОЗИЦІЇ В СПИСКУ ---
class CartItem(Base):
    __tablename__ = 'cart_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(ForeignKey('shopping_lists.id'))
    product_sku: Mapped[str] = mapped_column(ForeignKey('products.sku'))
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    surplus_quantity: Mapped[float] = mapped_column(Float, default=0.0) 

    shopping_list = relationship("ShoppingList", back_populates="items")
    product = relationship("Product")

# --- 6. ФОТО ТОВАРІВ ---
class ProductPhoto(Base):
    __tablename__ = 'product_photos'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_sku: Mapped[str] = mapped_column(ForeignKey('products.sku'))
    file_id: Mapped[str] = mapped_column(String, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'))
    status: Mapped[str] = mapped_column(String, default='pending') 

    product = relationship("Product", back_populates="photos")
    author = relationship("User", back_populates="photos")

# --- 7. ГЛОБАЛЬНІ НАЛАШТУВАННЯ (НОВЕ!) ---
class BotSetting(Base):
    __tablename__ = 'bot_settings'

    key: Mapped[str] = mapped_column(String, primary_key=True) # Наприклад: 'search_filter_months'
    value: Mapped[str] = mapped_column(String) # Наприклад: '6'
    description: Mapped[str] = mapped_column(String, nullable=True) # Опис для адміна