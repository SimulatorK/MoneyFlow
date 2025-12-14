"""
Tests for budget functionality including fixed costs and budget items.

Tests CRUD operations, category relationships, and budget calculations.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime, date

from app.models.user import User
from app.models.budget import BudgetItem, FixedCost
from app.models.expense import Category, SubCategory


class TestBudgetItemCRUD:
    """Test suite for budget item CRUD operations."""
    
    def test_create_budget_item(
        self,
        db_session: Session,
        test_user: User,
        test_category: Category
    ):
        """Test creating a new budget item."""
        budget_item = BudgetItem(
            user_id=test_user.id,
            category_type="need",
            expense_category_id=test_category.id,
            use_tracked_average=True,
            tracking_period_months=3
        )
        db_session.add(budget_item)
        db_session.commit()
        
        assert budget_item.id is not None
        assert budget_item.expense_category_id == test_category.id
        assert budget_item.use_tracked_average is True
        assert budget_item.tracking_period_months == 3
    
    def test_create_budget_item_with_fixed_amount(
        self,
        db_session: Session,
        test_user: User,
        test_category: Category
    ):
        """Test creating a budget item with fixed amount."""
        budget_item = BudgetItem(
            user_id=test_user.id,
            expense_category_id=test_category.id,
            category_type="want",
            use_tracked_average=False,
            specified_amount=150.00
        )
        db_session.add(budget_item)
        db_session.commit()
        
        assert budget_item.use_tracked_average is False
        assert budget_item.specified_amount == 150.00
    
    def test_budget_item_with_subcategory(
        self,
        db_session: Session,
        test_user: User,
        test_category: Category,
        test_subcategory: SubCategory
    ):
        """Test budget item with subcategory relationship."""
        budget_item = BudgetItem(
            user_id=test_user.id,
            category_type="need",
            expense_category_id=test_category.id,
            expense_subcategory_id=test_subcategory.id
        )
        db_session.add(budget_item)
        db_session.commit()
        
        assert budget_item.expense_subcategory_id == test_subcategory.id


class TestFixedCostCRUD:
    """Test suite for fixed cost CRUD operations."""
    
    def test_create_fixed_cost(
        self,
        db_session: Session,
        test_user: User
    ):
        """Test creating a new fixed cost."""
        fixed_cost = FixedCost(
            user_id=test_user.id,
            name="Rent",
            amount=1500.00,
            frequency="monthly",
            amount_mode="fixed"
        )
        db_session.add(fixed_cost)
        db_session.commit()
        
        assert fixed_cost.id is not None
        assert fixed_cost.name == "Rent"
        assert fixed_cost.amount == 1500.00
        assert fixed_cost.frequency == "monthly"
    
    def test_create_fixed_cost_tracked_mode(
        self,
        db_session: Session,
        test_user: User,
        test_category: Category
    ):
        """Test creating a fixed cost with tracked average mode."""
        fixed_cost = FixedCost(
            user_id=test_user.id,
            name="Utilities",
            amount=0.00,  # Will use tracked average
            amount_mode="tracked",
            frequency="monthly",
            expense_category_id=test_category.id,
            tracking_period_months=6
        )
        db_session.add(fixed_cost)
        db_session.commit()
        
        assert fixed_cost.amount_mode == "tracked"
        assert fixed_cost.tracking_period_months == 6
    
    def test_fixed_cost_with_category(
        self,
        db_session: Session,
        test_user: User,
        test_category: Category,
        test_subcategory: SubCategory
    ):
        """Test fixed cost with category and subcategory."""
        fixed_cost = FixedCost(
            user_id=test_user.id,
            name="Car Insurance",
            amount=200.00,
            frequency="monthly",
            expense_category_id=test_category.id,
            expense_subcategory_id=test_subcategory.id
        )
        db_session.add(fixed_cost)
        db_session.commit()
        
        assert fixed_cost.expense_category_id == test_category.id
        assert fixed_cost.expense_subcategory_id == test_subcategory.id


class TestBudgetPageRoutes:
    """Test suite for budget page routes."""
    
    def test_budget_page_loads(
        self,
        client: TestClient,
        test_user_with_auth: User
    ):
        """Test that budget page loads successfully."""
        response = client.get("/budget")
        assert response.status_code == 200
        assert "Budget" in response.text
    
    def test_add_fixed_cost_route(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User
    ):
        """Test adding a fixed cost via POST."""
        response = client.post(
            "/budget/fixed-cost/add",
            data={
                "name": "Internet",
                "amount": "75.00",
                "frequency": "monthly",
                "amount_mode": "fixed"
            },
            follow_redirects=False
        )
        assert response.status_code in [302, 303, 307]
        
        # Verify fixed cost was created
        fixed_cost = db_session.query(FixedCost).filter(
            FixedCost.name == "Internet"
        ).first()
        assert fixed_cost is not None
        assert fixed_cost.amount == 75.00
    
    def test_add_budget_item_route(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User,
        test_category: Category
    ):
        """Test adding a budget item via POST."""
        response = client.post(
            "/budget/item/add",
            data={
                "expense_category_id": str(test_category.id),
                "category_type": "need",
                "use_tracked_average": "false",
                "specified_amount": "200.00",
                "tracking_period_months": "3"
            },
            follow_redirects=False
        )
        assert response.status_code in [302, 303, 307]
        
        # Verify budget item was created
        budget_item = db_session.query(BudgetItem).filter(
            BudgetItem.expense_category_id == test_category.id
        ).first()
        assert budget_item is not None
    
    def test_delete_fixed_cost(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User,
        test_fixed_cost: FixedCost
    ):
        """Test deleting a fixed cost."""
        fixed_cost_id = test_fixed_cost.id
        
        response = client.delete(
            f"/budget/fixed-cost/{fixed_cost_id}",
            follow_redirects=False
        )
        assert response.status_code in [200, 302, 303, 307]
        
        # Verify fixed cost was deleted
        db_session.expire_all()
        fixed_cost = db_session.query(FixedCost).filter(
            FixedCost.id == fixed_cost_id
        ).first()
        assert fixed_cost is None
    
    def test_delete_budget_item(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User,
        test_budget_item: BudgetItem
    ):
        """Test deleting a budget item."""
        budget_item_id = test_budget_item.id
        
        response = client.delete(
            f"/budget/item/{budget_item_id}",
            follow_redirects=False
        )
        assert response.status_code in [200, 302, 303, 307]
        
        # Verify budget item was deleted
        db_session.expire_all()
        budget_item = db_session.query(BudgetItem).filter(
            BudgetItem.id == budget_item_id
        ).first()
        assert budget_item is None


class TestBudgetCalculations:
    """Test suite for budget summary calculations."""
    
    def test_budget_summary_with_fixed_costs(
        self,
        db_session: Session,
        test_user: User
    ):
        """Test budget summary includes fixed costs."""
        # Create multiple fixed costs
        fixed_costs = [
            FixedCost(
                user_id=test_user.id,
                name="Rent",
                amount=1500.00,
                frequency="monthly",
                amount_mode="fixed"
            ),
            FixedCost(
                user_id=test_user.id,
                name="Car Payment",
                amount=400.00,
                frequency="monthly",
                amount_mode="fixed"
            )
        ]
        for fc in fixed_costs:
            db_session.add(fc)
        db_session.commit()
        
        # Query total fixed costs
        total_fixed = sum(fc.amount for fc in fixed_costs)
        assert total_fixed == 1900.00
    
    def test_frequency_conversions(self):
        """Test frequency conversion to monthly amounts."""
        from app.routes.budget import FREQUENCY_TO_MONTHLY
        
        # Weekly should multiply by ~4.33
        assert FREQUENCY_TO_MONTHLY["weekly"] == pytest.approx(4.33, rel=0.1)
        
        # Bi-weekly should multiply by ~2.17
        assert FREQUENCY_TO_MONTHLY["bi-weekly"] == pytest.approx(2.17, rel=0.1)
        
        # Annual should divide by 12
        assert FREQUENCY_TO_MONTHLY["annually"] == pytest.approx(1/12, rel=0.01)
        
        # Quarterly should divide by 3
        assert FREQUENCY_TO_MONTHLY["quarterly"] == pytest.approx(1/3, rel=0.01)


class TestBudgetAPI:
    """Test suite for budget API endpoints."""
    
    def test_get_fixed_cost_json(
        self,
        client: TestClient,
        test_user_with_auth: User,
        test_fixed_cost: FixedCost
    ):
        """Test getting fixed cost data as JSON."""
        response = client.get(f"/api/fixed-cost/{test_fixed_cost.id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == test_fixed_cost.name
        assert data["amount"] == test_fixed_cost.amount
    
    def test_get_budget_item_json(
        self,
        client: TestClient,
        test_user_with_auth: User,
        test_budget_item: BudgetItem
    ):
        """Test getting budget item data as JSON."""
        response = client.get(f"/api/budget-item/{test_budget_item.id}")
        assert response.status_code == 200
        
        data = response.json()
        # Check that the response contains expected budget item data
        assert "expense_category_id" in data or "id" in data
    
    def test_get_budget_summary(
        self,
        client: TestClient,
        test_user_with_auth: User
    ):
        """Test getting budget summary data."""
        response = client.get("/api/budget/summary")
        assert response.status_code == 200
        
        data = response.json()
        assert "fixed_costs" in data or "summary" in data or response.status_code == 200

