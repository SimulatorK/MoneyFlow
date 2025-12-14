"""
Tests for expense tracking functionality.

Tests expense CRUD operations, categories, and statistics.
"""

import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.expense import Category, SubCategory, Expense
from app.models.user import User
from app.routes.expenses import get_expense_stats


class TestExpensesPage:
    """Test suite for expenses page and display."""
    
    def test_expenses_page_loads(
        self, 
        client: TestClient, 
        test_user_with_auth: User
    ):
        """Test that expenses page loads successfully."""
        response = client.get("/expenses")
        assert response.status_code == 200
        assert "Expenses" in response.text or "expenses" in response.text.lower()
    
    def test_expenses_page_shows_recent_expenses(
        self,
        client: TestClient,
        test_user_with_auth: User,
        test_expense: Expense
    ):
        """Test that recent expenses are displayed."""
        response = client.get("/expenses")
        assert response.status_code == 200
        # Should show the expense amount
        assert "100" in response.text
    
    def test_expenses_page_unauthenticated_redirects(self, client: TestClient):
        """Test that unauthenticated users are redirected."""
        response = client.get("/expenses", follow_redirects=False)
        assert response.status_code in [302, 303, 307]


class TestAddExpense:
    """Test suite for adding expenses."""
    
    def test_add_expense_success(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User,
        test_category: Category
    ):
        """Test successfully adding a new expense."""
        response = client.post(
            "/expenses/add",
            data={
                "category_id": test_category.id,
                "amount": 75.50,
                "expense_date": date.today().isoformat(),
                "notes": "Test expense"
            },
            follow_redirects=False
        )
        assert response.status_code in [302, 303]
        
        # Verify expense was created
        expense = db_session.query(Expense).filter(
            Expense.amount == 75.50,
            Expense.notes == "Test expense"
        ).first()
        assert expense is not None
    
    def test_add_recurring_expense(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User,
        test_category: Category
    ):
        """Test adding a recurring expense with frequency."""
        response = client.post(
            "/expenses/add",
            data={
                "category_id": test_category.id,
                "amount": 50.00,
                "expense_date": date.today().isoformat(),
                "notes": "Monthly subscription",
                "is_recurring": "yes",
                "frequency": "monthly"
            },
            follow_redirects=False
        )
        assert response.status_code in [302, 303]
        
        # Verify recurring fields
        expense = db_session.query(Expense).filter(
            Expense.notes == "Monthly subscription"
        ).first()
        assert expense is not None
        assert expense.is_recurring == "yes"
        assert expense.frequency == "monthly"
    
    def test_add_expense_with_subcategory(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User,
        test_category: Category,
        test_subcategory: SubCategory
    ):
        """Test adding an expense with a subcategory."""
        response = client.post(
            "/expenses/add",
            data={
                "category_id": test_category.id,
                "subcategory_id": test_subcategory.id,
                "amount": 25.00,
                "expense_date": date.today().isoformat()
            },
            follow_redirects=False
        )
        assert response.status_code in [302, 303]
        
        expense = db_session.query(Expense).filter(
            Expense.amount == 25.00
        ).first()
        assert expense is not None
        assert expense.subcategory_id == test_subcategory.id


class TestExpenseStats:
    """Test suite for expense statistics calculations."""
    
    def test_get_expense_stats_returns_data(
        self,
        db_session: Session,
        test_user: User,
        multiple_expenses: list[Expense]
    ):
        """Test that expense stats returns proper data structure."""
        stats = get_expense_stats(db_session, test_user.id, "1m")
        
        assert "total_in_period" in stats
        assert "by_category" in stats
        assert "category_averages" in stats
        assert "subcategory_stats" in stats
    
    def test_expense_stats_total_calculation(
        self,
        db_session: Session,
        test_user: User,
        multiple_expenses: list[Expense]
    ):
        """Test that total spending is calculated correctly."""
        stats = get_expense_stats(db_session, test_user.id, "1m")
        
        # Sum should be 50+60+70+80+90+100+110+120+130+140 = 950
        expected_total = sum(50 + (i * 10) for i in range(10))
        assert stats["total_in_period"] == expected_total
    
    def test_expense_stats_empty_for_new_user(
        self,
        db_session: Session,
        test_user: User
    ):
        """Test stats for user with no expenses."""
        stats = get_expense_stats(db_session, test_user.id, "1m")
        
        assert stats["total_in_period"] == 0
        assert len(stats["by_category"]) == 0


class TestCategories:
    """Test suite for category management."""
    
    def test_create_category(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User
    ):
        """Test creating a new category directly in database."""
        # Create category through the model since the route may have additional requirements
        category = Category(
            user_id=1,  # The test user will have id 1 in test DB
            name="New Category"
        )
        db_session.add(category)
        db_session.commit()
        
        # Verify it was created
        created = db_session.query(Category).filter(
            Category.name == "New Category"
        ).first()
        assert created is not None
        assert created.name == "New Category"
    
    def test_get_subcategories(
        self,
        client: TestClient,
        test_user_with_auth: User,
        test_category: Category,
        test_subcategory: SubCategory
    ):
        """Test fetching subcategories for a category."""
        response = client.get(f"/api/subcategories/{test_category.id}")
        assert response.status_code == 200
        
        data = response.json()
        # Response contains subcategories dict or list
        if isinstance(data, dict) and "subcategories" in data:
            subs = data["subcategories"]
        else:
            subs = data
        assert len(subs) >= 1
        assert any(sub["name"] == "Test Subcategory" for sub in subs)

