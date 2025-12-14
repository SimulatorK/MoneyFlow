"""
Pytest fixtures and configuration for MoneyFlow tests.

This module provides common fixtures used across all test modules,
including database setup, test client, and mock data generators.
"""

import pytest
from datetime import date, datetime
from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db import get_db, Base
from app.models.user import User
from app.models.expense import Category, SubCategory, Expense
from app.models.income_taxes import IncomeTaxes
from app.models.budget import FixedCost, BudgetItem
from app.utils.auth import hash_password


# Create in-memory SQLite database for testing
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db() -> Generator[Session, None, None]:
    """Override database dependency for tests."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Create a fresh database session for each test.
    
    Creates all tables before the test and drops them after.
    """
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Create a test client with overridden database dependency.
    """
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """
    Create a test user in the database.
    """
    user = User(
        username="testuser",
        password_hash=hash_password("testpassword123"),
        name="Test User",
        dark_mode=False
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_with_auth(client: TestClient, test_user: User) -> User:
    """
    Create a test user and set authentication cookie.
    """
    client.cookies.set("username", test_user.username)
    return test_user


@pytest.fixture
def test_category(db_session: Session, test_user: User) -> Category:
    """
    Create a test expense category.
    """
    category = Category(
        user_id=test_user.id,
        name="Test Category"
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


@pytest.fixture
def test_subcategory(db_session: Session, test_category: Category) -> SubCategory:
    """
    Create a test expense subcategory.
    """
    subcategory = SubCategory(
        category_id=test_category.id,
        name="Test Subcategory"
    )
    db_session.add(subcategory)
    db_session.commit()
    db_session.refresh(subcategory)
    return subcategory


@pytest.fixture
def test_expense(
    db_session: Session, 
    test_user: User, 
    test_category: Category
) -> Expense:
    """
    Create a test expense entry.
    """
    expense = Expense(
        user_id=test_user.id,
        category_id=test_category.id,
        amount=100.00,
        expense_date=date.today(),
        notes="Test expense",
        is_recurring="no"
    )
    db_session.add(expense)
    db_session.commit()
    db_session.refresh(expense)
    return expense


@pytest.fixture
def test_income_taxes(db_session: Session, test_user: User) -> IncomeTaxes:
    """
    Create test income and tax data.
    """
    income = IncomeTaxes(
        user_id=test_user.id,
        tax_year=2025,
        filing_status="single",
        filing_state="MO",
        base_salary=100000.00,
        pay_frequency="bi-weekly"
    )
    db_session.add(income)
    db_session.commit()
    db_session.refresh(income)
    return income


@pytest.fixture
def test_fixed_cost(db_session: Session, test_user: User) -> FixedCost:
    """
    Create a test fixed cost entry.
    """
    cost = FixedCost(
        user_id=test_user.id,
        name="Test Rent",
        amount=1500.00,
        frequency="monthly",
        category_type="need",
        is_active=True
    )
    db_session.add(cost)
    db_session.commit()
    db_session.refresh(cost)
    return cost


@pytest.fixture
def test_budget_item(db_session: Session, test_user: User, test_category: Category) -> BudgetItem:
    """
    Create a test budget item entry.
    """
    item = BudgetItem(
        user_id=test_user.id,
        expense_category_id=test_category.id,
        use_tracked_average=False,
        specified_amount=200.00,
        tracking_period_months=3,
        category_type="need"
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


@pytest.fixture
def multiple_expenses(
    db_session: Session, 
    test_user: User, 
    test_category: Category
) -> list[Expense]:
    """
    Create multiple test expenses for statistics testing.
    """
    expenses = []
    for i in range(10):
        expense = Expense(
            user_id=test_user.id,
            category_id=test_category.id,
            amount=50.00 + (i * 10),  # 50, 60, 70, ... 140
            expense_date=date.today(),
            notes=f"Test expense {i+1}",
            is_recurring="no"
        )
        db_session.add(expense)
        expenses.append(expense)
    
    db_session.commit()
    return expenses

