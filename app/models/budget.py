from sqlalchemy import Column, Integer, Float, String, ForeignKey, Boolean, Date
from sqlalchemy.orm import relationship
from app.models import Base


class SubscriptionUtility(Base):
    """Track utilities and subscriptions over time."""
    __tablename__ = "subscription_utilities"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    utility_type = Column(String(50), default="subscription")  # subscription, utility, service
    category_type = Column(String(50), default="need")  # need, want
    is_active = Column(Boolean, default=True)
    notes = Column(String(500), nullable=True)
    
    # Optional link to expense category for auto-tracking
    expense_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    expense_subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=True)
    
    # Relationships
    payments = relationship("SubscriptionPayment", back_populates="subscription", cascade="all, delete-orphan")


class SubscriptionPayment(Base):
    """Individual payment records for subscriptions/utilities."""
    __tablename__ = "subscription_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("subscription_utilities.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_date = Column(Date, nullable=False)
    notes = Column(String(200), nullable=True)
    
    # Relationships
    subscription = relationship("SubscriptionUtility", back_populates="payments")


class BudgetCategory(Base):
    """Budget-specific categories (separate from expense tracking categories)."""
    __tablename__ = "budget_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    category_type = Column(String(50), default="need")  # need, want, savings, debt
    
    # Relationships
    fixed_costs = relationship("FixedCost", back_populates="budget_category", cascade="all, delete-orphan", foreign_keys="FixedCost.category_id")
    budget_items = relationship("BudgetItem", back_populates="category", cascade="all, delete-orphan")


class FixedCost(Base):
    """Fixed recurring costs (rent, utilities, subscriptions, etc.)."""
    __tablename__ = "fixed_costs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("budget_categories.id"), nullable=True)
    
    # Link to shared expense category (optional - for tracking)
    expense_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    expense_subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=True)
    
    name = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)  # Used as specified amount or as a fallback
    frequency = Column(String(50), default="monthly")  # weekly, bi-weekly, semi-monthly, monthly, quarterly, annually
    category_type = Column(String(50), default="need")  # need, want, savings, debt
    is_active = Column(Boolean, default=True)
    
    # Tracking mode: 'fixed' = use amount as-is, 'tracked' = use expense tracking average
    amount_mode = Column(String(20), default="fixed")  # 'fixed' or 'tracked'
    # If tracked, which average period to use (3, 6, or 12 months)
    tracking_period_months = Column(Integer, default=3)
    
    # Relationships
    budget_category = relationship("BudgetCategory", back_populates="fixed_costs")


class BudgetItem(Base):
    """
    Budget items that link expense categories to budget allocations.
    Can use either a specified amount or the tracked average from expenses.
    """
    __tablename__ = "budget_items"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Link to budget category
    budget_category_id = Column(Integer, ForeignKey("budget_categories.id"), nullable=True)
    
    # Link to expense category (from expenses page)
    expense_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    expense_subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=True)
    
    # Budget settings
    use_tracked_average = Column(Boolean, default=True)  # If false, use specified_amount
    specified_amount = Column(Float, default=0)
    tracking_period_months = Column(Integer, default=3)  # 3, 6, or 12 month average
    category_type = Column(String(50), default="need")  # need, want
    
    # Relationships
    category = relationship("BudgetCategory", back_populates="budget_items")

