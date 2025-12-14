from sqlalchemy import Column, Integer, Float, String, ForeignKey, Date, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import date, datetime
from app.models import Base


class Category(Base):
    """User-specific expense categories."""
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    
    # Relationships
    subcategories = relationship("SubCategory", back_populates="category", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="category")


class SubCategory(Base):
    """Sub-categories within a category."""
    __tablename__ = "subcategories"
    
    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String(100), nullable=False)
    
    # Relationships
    category = relationship("Category", back_populates="subcategories")
    expenses = relationship("Expense", back_populates="subcategory")


class Expense(Base):
    """
    Individual expense entries.
    
    Supports both one-time and recurring expenses. For recurring expenses,
    the frequency field specifies how often the expense occurs.
    """
    __tablename__ = "expenses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=True)
    
    amount = Column(Float, nullable=False)
    expense_date = Column(Date, nullable=False, default=date.today)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Recurring expense fields
    is_recurring = Column(String(10), default="no")  # yes/no
    frequency = Column(String(20), nullable=True)  # weekly, bi-weekly, monthly, quarterly, etc.
    
    # Relationships
    category = relationship("Category", back_populates="expenses")
    subcategory = relationship("SubCategory", back_populates="expenses")

