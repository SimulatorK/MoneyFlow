"""
Budget management routes for MoneyFlow application.

This module handles all budget-related functionality including:
- Fixed costs (recurring expenses like rent, utilities, subscriptions)
- Variable budget items (flexible spending categories)
- Budget summary calculations and projections
- Category and subcategory management for budget items

The budget system supports:
- Multiple payment frequencies (weekly, monthly, annually, etc.)
- Integration with expense tracking for "tracked average" budgeting
- 50/30/20 budgeting rule compliance tracking
- Net worth and cash flow projections

Routes:
    GET  /budget              - Main budget page
    POST /budget/fixed-cost/add    - Add new fixed cost
    POST /budget/fixed-cost/update/<id> - Update fixed cost
    DELETE /budget/fixed-cost/<id>  - Delete fixed cost
    POST /budget/item/add          - Add budget item
    POST /budget/item/update/<id>  - Update budget item
    DELETE /budget/item/<id>       - Delete budget item
    GET  /api/fixed-cost/<id>      - Get fixed cost JSON
    GET  /api/budget-item/<id>     - Get budget item JSON
    GET  /api/budget/summary       - Get full budget summary JSON
"""

from fastapi import APIRouter, Request, Form, Depends, Query, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta, datetime
from typing import Optional
import csv
import io
from app.db import get_db
from app.models.user import User
from app.models.income_taxes import IncomeTaxes
from app.models.expense import Category as ExpenseCategory, SubCategory, Expense
from app.models.budget import BudgetCategory, FixedCost, BudgetItem, SubscriptionUtility, SubscriptionPayment
from app.routes.income_taxes import calculate_taxes, PAY_PERIODS_PER_YEAR
from app.logging_config import get_logger
import base64

# Module logger for budget operations
logger = get_logger(__name__)

# Router and template configuration
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ============================================================================
# CONSTANTS
# ============================================================================

# Multipliers to convert payment frequencies to monthly amounts
# Example: $100/week * 4.333 = ~$433.30/month
FREQUENCY_TO_MONTHLY = {
    "weekly": 4.333,       # 52 weeks / 12 months
    "bi-weekly": 2.167,    # 26 payments / 12 months
    "semi-monthly": 2,     # 24 payments / 12 months
    "monthly": 1,          # Direct monthly amount
    "quarterly": 0.333,    # 4 payments / 12 months
    "bi-annual": 0.1667,  # 2 payments / 12 months
    "annually": 0.0833     # 1 payment / 12 months
}

# Available payment frequency options
FREQUENCIES = ["weekly", "bi-weekly", "semi-monthly", "monthly", "quarterly", 'bi-annual', "annually"]

# Budget category types following the 50/30/20 rule
# Needs: Essential expenses (50%)
# Wants: Discretionary spending (30%)
# Savings/Debt: Financial goals (20%)
CATEGORY_TYPES = [
    ("need", "Need"),
    ("want", "Want"),
    ("savings", "Savings"),
    ("debt", "Debt Payment"),
    # ("donation", "Donation")
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_current_user(request: Request, db: Session):
    """Get the logged-in user from cookies."""
    username = request.cookies.get("username")
    if not username:
        logger.debug("No username cookie found in request")
        return None
    user = db.query(User).filter(User.username == username).first()
    if user:
        logger.debug(f"Authenticated user: {username}")
    else:
        logger.warning(f"Username cookie exists but user not found: {username}")
    return user


def get_profile_picture_data(user):
    """Get base64 encoded profile picture data for templates."""
    if user and user.profile_picture and user.profile_picture_type:
        return base64.b64encode(user.profile_picture).decode('utf-8'), user.profile_picture_type
    return None, None


def get_expense_averages_multi(db: Session, user_id: int):
    """Get average monthly expenses by category over 3, 6, and 12 months."""
    today = date.today()
    
    result = {
        3: {"category": {}, "subcategory": {}, "category_only": {}},
        6: {"category": {}, "subcategory": {}, "category_only": {}},
        12: {"category": {}, "subcategory": {}, "category_only": {}}
    }
    
    for months in [3, 6, 12]:
        start_date = today - timedelta(days=months * 30)
        
        expenses = db.query(Expense).filter(
            Expense.user_id == user_id,
            Expense.expense_date >= start_date
        ).all()
        
        category_totals = {}
        subcategory_totals = {}
        category_only_totals = {}  # Expenses in category but without subcategory
        
        for expense in expenses:
            cat_id = expense.category_id
            subcat_id = expense.subcategory_id
            
            if cat_id:
                category_totals[cat_id] = category_totals.get(cat_id, 0) + expense.amount
                
                if subcat_id:
                    key = (cat_id, subcat_id)
                    subcategory_totals[key] = subcategory_totals.get(key, 0) + expense.amount
                else:
                    # Track expenses in category without subcategory
                    category_only_totals[cat_id] = category_only_totals.get(cat_id, 0) + expense.amount
        
        # Convert to monthly averages
        result[months]["category"] = {k: v / months for k, v in category_totals.items()}
        result[months]["subcategory"] = {k: v / months for k, v in subcategory_totals.items()}
        result[months]["category_only"] = {k: v / months for k, v in category_only_totals.items()}
    
    return result


def get_actual_spending_for_period(db: Session, user_id: int, lookback_months: int = 1):
    """Get actual spending for a specific lookback period, broken down by category and subcategory."""
    today = date.today()
    start_date = today - timedelta(days=lookback_months * 30)
    
    expenses = db.query(Expense).filter(
        Expense.user_id == user_id,
        Expense.expense_date >= start_date
    ).all()
    
    # By category
    by_category = {}
    by_subcategory = {}
    uncategorized_total = 0
    
    for expense in expenses:
        cat_id = expense.category_id
        subcat_id = expense.subcategory_id
        cat_name = expense.category.name if expense.category else "Uncategorized"
        
        if cat_id:
            if cat_id not in by_category:
                by_category[cat_id] = {
                    "name": cat_name,
                    "total": 0,
                    "subcategories": {}
                }
            by_category[cat_id]["total"] += expense.amount
            
            if subcat_id:
                subcat_name = expense.subcategory.name if expense.subcategory else "Unspecified"
                if subcat_id not in by_category[cat_id]["subcategories"]:
                    by_category[cat_id]["subcategories"][subcat_id] = {
                        "name": subcat_name,
                        "total": 0
                    }
                by_category[cat_id]["subcategories"][subcat_id]["total"] += expense.amount
                
                # Also track in flat structure
                key = (cat_id, subcat_id)
                if key not in by_subcategory:
                    by_subcategory[key] = {
                        "category_name": cat_name,
                        "subcategory_name": subcat_name,
                        "total": 0
                    }
                by_subcategory[key]["total"] += expense.amount
        else:
            uncategorized_total += expense.amount
    
    return {
        "by_category": by_category,
        "by_subcategory": by_subcategory,
        "uncategorized": uncategorized_total,
        "total": sum(e.amount for e in expenses)
    }


def calculate_budget_vs_actual(db: Session, user_id: int, summary: dict, actual_spending: dict, lookback_months: int):
    """
    Calculate comparison between budgeted amounts and actual spending.
    Fixed expenses are assumed to be spent as budgeted (not tracked via expenses).
    Variable expenses are compared to actual spending.
    """
    comparisons = []
    unbudgeted_expenses = []
    
    # Get all expense categories the user has spent in
    spent_categories = set(actual_spending["by_category"].keys())
    
    # Track which categories are covered by budget items
    budgeted_category_keys = set()  # (cat_id, subcat_id or None)
    
    # Process variable budget items
    for item in summary.get("budget_items", []):
        cat_id = item.get("expense_category_id")
        subcat_id = item.get("expense_subcategory_id")
        budgeted = item.get("monthly_amount", 0) * lookback_months
        
        if cat_id:
            if subcat_id:
                # Specific subcategory
                budgeted_category_keys.add((cat_id, subcat_id))
                key = (cat_id, subcat_id)
                actual = actual_spending["by_subcategory"].get(key, {}).get("total", 0)
            else:
                # Whole category
                budgeted_category_keys.add((cat_id, None))
                actual = actual_spending["by_category"].get(cat_id, {}).get("total", 0)
            
            diff = budgeted - actual
            pct = (actual / budgeted * 100) if budgeted > 0 else (100 if actual > 0 else 0)
            
            comparisons.append({
                "name": item.get("category_name", "Unknown") + (f" > {item.get('subcategory_name')}" if item.get("subcategory_name") else ""),
                "category_type": item.get("category_type", "need"),
                "budgeted": budgeted,
                "actual": actual,
                "difference": diff,
                "percentage": pct,
                "is_over": actual > budgeted,
                "is_variable": True
            })
    
    # Find unbudgeted categories (expenses in categories not in the budget)
    for cat_id, cat_data in actual_spending["by_category"].items():
        # Check if this category is fully covered
        if (cat_id, None) in budgeted_category_keys:
            continue
        
        # Check if all subcategories are covered
        subcats_covered = True
        for subcat_id in cat_data.get("subcategories", {}).keys():
            if (cat_id, subcat_id) not in budgeted_category_keys:
                subcats_covered = False
                break
        
        if not subcats_covered:
            # Some or all spending in this category is unbudgeted
            unbudgeted_amount = cat_data["total"]
            # Subtract any budgeted subcategories
            for subcat_id in cat_data.get("subcategories", {}).keys():
                if (cat_id, subcat_id) in budgeted_category_keys:
                    unbudgeted_amount -= cat_data["subcategories"][subcat_id]["total"]
            
            if unbudgeted_amount > 0:
                unbudgeted_expenses.append({
                    "category_name": cat_data["name"],
                    "amount": unbudgeted_amount,
                    "subcategories": [
                        {"name": s["name"], "amount": s["total"]}
                        for sid, s in cat_data.get("subcategories", {}).items()
                        if (cat_id, sid) not in budgeted_category_keys
                    ]
                })
    
    # Add uncategorized expenses
    if actual_spending.get("uncategorized", 0) > 0:
        unbudgeted_expenses.append({
            "category_name": "Uncategorized",
            "amount": actual_spending["uncategorized"],
            "subcategories": []
        })
    
    # Sort comparisons by how over budget they are
    comparisons.sort(key=lambda x: x["percentage"], reverse=True)
    
    # Calculate totals
    total_budgeted = sum(c["budgeted"] for c in comparisons)
    total_actual = sum(c["actual"] for c in comparisons)
    total_unbudgeted = sum(u["amount"] for u in unbudgeted_expenses)
    
    return {
        "comparisons": comparisons,
        "unbudgeted": unbudgeted_expenses,
        "total_unbudgeted": total_unbudgeted,
        "total_budgeted": total_budgeted,
        "total_actual": total_actual,
        "lookback_months": lookback_months
    }


def get_expense_averages(db: Session, user_id: int, months: int = 3):
    """Get average monthly expenses by category over the last N months."""
    start_date = date.today() - timedelta(days=months * 30)
    
    expenses = db.query(Expense).filter(
        Expense.user_id == user_id,
        Expense.expense_date >= start_date
    ).all()
    
    category_totals = {}
    subcategory_totals = {}
    
    for expense in expenses:
        cat_id = expense.category_id
        subcat_id = expense.subcategory_id
        
        if cat_id:
            category_totals[cat_id] = category_totals.get(cat_id, 0) + expense.amount
            
        if subcat_id:
            key = (cat_id, subcat_id)
            subcategory_totals[key] = subcategory_totals.get(key, 0) + expense.amount
    
    # Convert to monthly averages
    category_averages = {k: v / months for k, v in category_totals.items()}
    subcategory_averages = {k: v / months for k, v in subcategory_totals.items()}
    
    return category_averages, subcategory_averages


def calculate_budget_summary(db: Session, user_id: int, income_data):
    """Calculate complete budget summary including all income sources."""
    # Get income data
    if income_data:
        calculated = calculate_taxes(income_data)
        if calculated:
            # Include ALL income sources for budgeting (taxable + non-taxable)
            gross_taxable = calculated.get("gross_income", 0)  # All taxable income
            gross_nontaxable = calculated.get("total_nontaxable_income", 0)  # Roth distributions, etc.
            gross_monthly = (gross_taxable + gross_nontaxable) / 12
            
            # Net monthly = gross - taxes - pretax deductions - retirement contributions
            total_taxes = calculated.get("total_taxes", 0)
            pretax_deductions = calculated.get("pretax_deductions_annual", 0)
            pretax_retirement = calculated.get("pretax_retirement", 0)
            aftertax_retirement = calculated.get("aftertax_retirement", 0)
            net_monthly = (gross_taxable + gross_nontaxable - total_taxes - pretax_deductions - pretax_retirement - aftertax_retirement) / 12
            
            total_retirement_monthly = calculated.get("employee_contributions", 0) / 12
        else:
            gross_monthly = 0
            net_monthly = 0
            total_retirement_monthly = 0
    else:
        gross_monthly = 0
        net_monthly = 0
        total_retirement_monthly = 0
        calculated = None
    
    # Get expense averages for all periods (for tracked amounts)
    expense_avgs = get_expense_averages_multi(db, user_id)
    
    # Get fixed costs
    fixed_costs = db.query(FixedCost).filter(
        FixedCost.user_id == user_id,
        FixedCost.is_active == True
    ).all()
    
    fixed_costs_monthly = {}
    fixed_costs_by_type = {"need": 0, "want": 0, "savings": 0, "debt": 0}
    fixed_costs_details = []  # For detailed display
    
    for cost in fixed_costs:
        multiplier = FREQUENCY_TO_MONTHLY.get(cost.frequency, 1)
        
        # Determine amount based on mode
        amount_mode = cost.amount_mode or "fixed"
        tracking_months = cost.tracking_period_months or 3
        
        if amount_mode == "tracked" and cost.expense_category_id:
            # Use tracked average from expense data
            if cost.expense_subcategory_id:
                tracked_amount = expense_avgs[tracking_months]["subcategory"].get(
                    (cost.expense_category_id, cost.expense_subcategory_id), 0
                )
            else:
                tracked_amount = expense_avgs[tracking_months]["category"].get(
                    cost.expense_category_id, 0
                )
            monthly_amount = tracked_amount
            display_amount = tracked_amount
            using_tracked = True
        else:
            # Use fixed amount
            monthly_amount = cost.amount * multiplier
            display_amount = cost.amount
            using_tracked = False
        
        fixed_costs_monthly[cost.id] = monthly_amount
        fixed_costs_by_type[cost.category_type] = fixed_costs_by_type.get(cost.category_type, 0) + monthly_amount
        
        # Get linked category name
        linked_cat_name = None
        if cost.expense_category_id:
            cat = db.query(ExpenseCategory).filter(ExpenseCategory.id == cost.expense_category_id).first()
            linked_cat_name = cat.name if cat else None
        
        fixed_costs_details.append({
            "id": cost.id,
            "name": cost.name,
            "amount": cost.amount,
            "frequency": cost.frequency,
            "category_type": cost.category_type,
            "amount_mode": amount_mode,
            "tracking_period_months": tracking_months,
            "monthly_amount": monthly_amount,
            "using_tracked": using_tracked,
            "expense_category_id": cost.expense_category_id,
            "linked_category_name": linked_cat_name,
            "tracked_3mo": expense_avgs[3]["category"].get(cost.expense_category_id, 0) if cost.expense_category_id else 0,
            "tracked_6mo": expense_avgs[6]["category"].get(cost.expense_category_id, 0) if cost.expense_category_id else 0,
            "tracked_12mo": expense_avgs[12]["category"].get(cost.expense_category_id, 0) if cost.expense_category_id else 0
        })
    
    total_fixed_monthly = sum(fixed_costs_monthly.values())
    
    # Get budget items (expense categories with budgets)
    budget_items = db.query(BudgetItem).filter(BudgetItem.user_id == user_id).all()
    
    # Get expense averages (deprecated - we use expense_avgs now with specific periods)
    category_averages, subcategory_averages = get_expense_averages(db, user_id, months=3)
    
    variable_costs_by_type = {"need": 0, "want": 0}
    budget_item_details = []
    
    for item in budget_items:
        tracking_months = item.tracking_period_months or 3
        
        if item.use_tracked_average:
            if item.expense_subcategory_id:
                amount = expense_avgs[tracking_months]["subcategory"].get(
                    (item.expense_category_id, item.expense_subcategory_id), 0
                )
            elif item.expense_category_id:
                amount = expense_avgs[tracking_months]["category"].get(item.expense_category_id, 0)
            else:
                amount = 0
        else:
            amount = item.specified_amount or 0
        
        # Get category/subcategory names
        cat_name = ""
        subcat_name = ""
        if item.expense_category_id:
            cat = db.query(ExpenseCategory).filter(ExpenseCategory.id == item.expense_category_id).first()
            cat_name = cat.name if cat else "Unknown"
        if item.expense_subcategory_id:
            subcat = db.query(SubCategory).filter(SubCategory.id == item.expense_subcategory_id).first()
            subcat_name = subcat.name if subcat else ""
        
        variable_costs_by_type[item.category_type] = variable_costs_by_type.get(item.category_type, 0) + amount
        
        budget_item_details.append({
            "id": item.id,
            "expense_category_id": item.expense_category_id,
            "expense_subcategory_id": item.expense_subcategory_id,
            "category_name": cat_name,
            "subcategory_name": subcat_name,
            "use_tracked_average": item.use_tracked_average,
            "tracking_period_months": tracking_months,
            "tracked_3mo": expense_avgs[3]["category"].get(item.expense_category_id, 0) if item.expense_category_id else 0,
            "tracked_6mo": expense_avgs[6]["category"].get(item.expense_category_id, 0) if item.expense_category_id else 0,
            "tracked_12mo": expense_avgs[12]["category"].get(item.expense_category_id, 0) if item.expense_category_id else 0,
            "specified_amount": item.specified_amount,
            "monthly_amount": amount,
            "category_type": item.category_type
        })
    
    total_variable_monthly = sum(variable_costs_by_type.values())
    
    # Calculate totals
    total_needs = fixed_costs_by_type["need"] + variable_costs_by_type.get("need", 0)
    total_wants = fixed_costs_by_type["want"] + variable_costs_by_type.get("want", 0)
    total_savings = fixed_costs_by_type["savings"] + total_retirement_monthly
    total_debt = fixed_costs_by_type["debt"]
    
    total_expenses = total_fixed_monthly + total_variable_monthly
    
    # Calculate unbudgeted expenses from last month
    # Get all budgeted category/subcategory combinations
    budgeted_category_keys = set()
    for cost in fixed_costs:
        if cost.expense_category_id:
            budgeted_category_keys.add((cost.expense_category_id, cost.expense_subcategory_id))
    for item in budget_item_details:
        if item.get("expense_category_id"):
            budgeted_category_keys.add((item.get("expense_category_id"), item.get("expense_subcategory_id")))
    
    # Get last month's expenses
    today = date.today()
    one_month_ago = today - timedelta(days=30)
    recent_expenses = db.query(Expense).filter(
        Expense.user_id == user_id,
        Expense.expense_date >= one_month_ago
    ).all()
    
    # Calculate unbudgeted spending
    unbudgeted_monthly = 0
    unbudgeted_details = []
    category_unbudgeted = {}
    
    for expense in recent_expenses:
        cat_id = expense.category_id
        subcat_id = expense.subcategory_id
        
        # Check if this expense is covered by budget
        is_budgeted = False
        if cat_id:
            # Check if whole category is budgeted
            if (cat_id, None) in budgeted_category_keys:
                is_budgeted = True
            # Check if specific subcategory is budgeted
            elif (cat_id, subcat_id) in budgeted_category_keys:
                is_budgeted = True
        
        if not is_budgeted and expense.amount > 0:
            unbudgeted_monthly += expense.amount
            key = (cat_id, subcat_id)
            if key not in category_unbudgeted:
                cat_name = expense.category.name if expense.category else "Uncategorized"
                subcat_name = expense.subcategory.name if expense.subcategory else None
                category_unbudgeted[key] = {
                    "category_name": cat_name,
                    "subcategory_name": subcat_name,
                    "amount": 0
                }
            category_unbudgeted[key]["amount"] += expense.amount
    
    unbudgeted_details = sorted(category_unbudgeted.values(), key=lambda x: -x["amount"])
    
    # Calculate leftover including unbudgeted expenses
    leftover_before_unbudgeted = net_monthly - total_expenses
    leftover = leftover_before_unbudgeted - unbudgeted_monthly
    total_savings += max(0, leftover)  # Only add positive leftover to savings
    
    # Percentages
    needs_pct = (total_needs / gross_monthly * 100) if gross_monthly > 0 else 0
    wants_pct = (total_wants / gross_monthly * 100) if gross_monthly > 0 else 0
    savings_pct = (total_savings / gross_monthly * 100) if gross_monthly > 0 else 0
    debt_pct = (total_debt / gross_monthly * 100) if gross_monthly > 0 else 0
    
    return {
        "income": calculated,
        "gross_monthly": gross_monthly,
        "net_monthly": net_monthly,
        "total_retirement_monthly": total_retirement_monthly,
        "fixed_costs": fixed_costs,
        "fixed_costs_monthly": fixed_costs_monthly,
        "fixed_costs_by_type": fixed_costs_by_type,
        "fixed_costs_details": fixed_costs_details,
        "total_fixed_monthly": total_fixed_monthly,
        "budget_items": budget_item_details,
        "variable_costs_by_type": variable_costs_by_type,
        "total_variable_monthly": total_variable_monthly,
        "total_needs": total_needs,
        "total_wants": total_wants,
        "total_savings": total_savings,
        "total_debt": total_debt,
        "total_expenses": total_expenses,
        "leftover": leftover,
        "leftover_before_unbudgeted": leftover_before_unbudgeted,
        "unbudgeted_monthly": unbudgeted_monthly,
        "unbudgeted_details": unbudgeted_details,
        "needs_pct": needs_pct,
        "wants_pct": wants_pct,
        "savings_pct": savings_pct,
        "debt_pct": debt_pct,
        "category_averages": category_averages,
        "subcategory_averages": subcategory_averages,
        "expense_avgs": expense_avgs
    }


@router.get("/budget")
def budget_page(request: Request, db: Session = Depends(get_db), lookback: int = Query(1), error: Optional[str] = Query(None), success: Optional[str] = Query(None), tab: str = Query("budget")):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Get income data
    income_data = db.query(IncomeTaxes).filter(IncomeTaxes.user_id == user.id).first()
    
    # Get budget categories
    budget_categories = db.query(BudgetCategory).filter(BudgetCategory.user_id == user.id).all()
    
    # Get expense categories (for linking)
    expense_categories = db.query(ExpenseCategory).filter(ExpenseCategory.user_id == user.id).order_by(ExpenseCategory.name).all()
    
    # Calculate budget summary
    summary = calculate_budget_summary(db, user.id, income_data)
    
    # Get fixed costs
    fixed_costs = db.query(FixedCost).filter(FixedCost.user_id == user.id).order_by(FixedCost.category_type, FixedCost.name).all()
    
    # Get budget items
    budget_items = db.query(BudgetItem).filter(BudgetItem.user_id == user.id).all()
    
    # Get actual spending for selected lookback period
    actual_spending = get_actual_spending_for_period(db, user.id, lookback)
    
    # Calculate budget vs actual comparison
    budget_vs_actual = calculate_budget_vs_actual(db, user.id, summary, actual_spending, lookback)
    
    # Get subscription/utility data
    subscription_stats = get_subscription_stats(db, user.id)
    subscriptions = db.query(SubscriptionUtility).filter(
        SubscriptionUtility.user_id == user.id
    ).order_by(SubscriptionUtility.name).all()
    
    profile_picture_b64, profile_picture_type = get_profile_picture_data(user)
    
    return templates.TemplateResponse("budget.html", {
        "request": request,
        "title": "Budget",
        "user": user,
        "budget_categories": budget_categories,
        "expense_categories": expense_categories,
        "fixed_costs": fixed_costs,
        "budget_items": budget_items,
        "summary": summary,
        "frequencies": FREQUENCIES,
        "category_types": CATEGORY_TYPES,
        "frequency_to_monthly": FREQUENCY_TO_MONTHLY,
        "actual_spending": actual_spending,
        "budget_vs_actual": budget_vs_actual,
        "lookback_months": lookback,
        "profile_picture_b64": profile_picture_b64,
        "profile_picture_type": profile_picture_type,
        "dark_mode": user.dark_mode,
        "error": error,
        "success": success,
        "active_tab": tab,
        "subscriptions": subscriptions,
        "subscription_stats": subscription_stats,
        "utility_types": UTILITY_TYPES
    })


@router.post("/budget/fixed-cost/add")
def add_fixed_cost(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    amount: float = Form(0),
    frequency: str = Form("monthly"),
    category_type: str = Form("need"),
    expense_category_id: Optional[int] = Form(None),
    expense_subcategory_id: Optional[int] = Form(None),
    amount_mode: str = Form("fixed"),
    tracking_period_months: int = Form(3)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Normalize IDs
    cat_id = expense_category_id if expense_category_id and expense_category_id > 0 else None
    subcat_id = expense_subcategory_id if expense_subcategory_id and expense_subcategory_id > 0 else None
    
    # Check for duplicate category/subcategory in fixed costs
    if cat_id:
        existing_fixed = db.query(FixedCost).filter(
            FixedCost.user_id == user.id,
            FixedCost.expense_category_id == cat_id,
            FixedCost.expense_subcategory_id == subcat_id,
            FixedCost.is_active == True
        ).first()
        
        if existing_fixed:
            return RedirectResponse("/budget?error=duplicate_category", status_code=303)
        
        # Also check variable expenses (BudgetItem)
        existing_budget = db.query(BudgetItem).filter(
            BudgetItem.user_id == user.id,
            BudgetItem.expense_category_id == cat_id,
            BudgetItem.expense_subcategory_id == subcat_id
        ).first()
        
        if existing_budget:
            return RedirectResponse("/budget?error=duplicate_category", status_code=303)
    
    fixed_cost = FixedCost(
        user_id=user.id,
        name=name.strip(),
        amount=amount,
        frequency=frequency,
        category_type=category_type,
        expense_category_id=cat_id,
        expense_subcategory_id=subcat_id,
        amount_mode=amount_mode,
        tracking_period_months=tracking_period_months,
        is_active=True
    )
    db.add(fixed_cost)
    db.commit()
    
    return RedirectResponse("/budget", status_code=303)


@router.get("/api/fixed-cost/{cost_id}")
def get_fixed_cost(cost_id: int, request: Request, db: Session = Depends(get_db)):
    """Get a single fixed cost for editing."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    cost = db.query(FixedCost).filter(
        FixedCost.id == cost_id,
        FixedCost.user_id == user.id
    ).first()
    
    if not cost:
        return JSONResponse({"error": "Not found"}, status_code=404)
    
    return JSONResponse({
        "id": cost.id,
        "name": cost.name,
        "amount": cost.amount,
        "frequency": cost.frequency,
        "category_type": cost.category_type,
        "expense_category_id": cost.expense_category_id,
        "expense_subcategory_id": cost.expense_subcategory_id,
        "amount_mode": cost.amount_mode or "fixed",
        "tracking_period_months": cost.tracking_period_months or 3
    })


@router.post("/budget/fixed-cost/update/{cost_id}")
def update_fixed_cost(
    cost_id: int,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    amount: float = Form(0),
    frequency: str = Form("monthly"),
    category_type: str = Form("need"),
    expense_category_id: Optional[int] = Form(None),
    expense_subcategory_id: Optional[int] = Form(None),
    amount_mode: str = Form("fixed"),
    tracking_period_months: int = Form(3)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    cost = db.query(FixedCost).filter(
        FixedCost.id == cost_id,
        FixedCost.user_id == user.id
    ).first()
    
    if cost:
        cost.name = name.strip()
        cost.amount = amount
        cost.frequency = frequency
        cost.category_type = category_type
        cost.expense_category_id = expense_category_id if expense_category_id and expense_category_id > 0 else None
        cost.expense_subcategory_id = expense_subcategory_id if expense_subcategory_id and expense_subcategory_id > 0 else None
        cost.amount_mode = amount_mode
        cost.tracking_period_months = tracking_period_months
        db.commit()
    
    return RedirectResponse("/budget", status_code=303)


@router.delete("/budget/fixed-cost/{cost_id}")
def delete_fixed_cost(cost_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    cost = db.query(FixedCost).filter(
        FixedCost.id == cost_id,
        FixedCost.user_id == user.id
    ).first()
    
    if cost:
        db.delete(cost)
        db.commit()
        return JSONResponse({"success": True})
    
    return JSONResponse({"error": "Not found"}, status_code=404)


@router.post("/budget/item/add")
def add_budget_item(
    request: Request,
    db: Session = Depends(get_db),
    expense_category_id: int = Form(...),
    expense_subcategory_id: Optional[int] = Form(None),
    use_tracked_average: bool = Form(True),
    specified_amount: float = Form(0),
    tracking_period_months: int = Form(3),
    category_type: str = Form("need")
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Normalize subcategory ID
    subcat_id = expense_subcategory_id if expense_subcategory_id else None
    
    # Check if this category/subcategory already exists in fixed costs
    existing_fixed = db.query(FixedCost).filter(
        FixedCost.user_id == user.id,
        FixedCost.expense_category_id == expense_category_id,
        FixedCost.expense_subcategory_id == subcat_id,
        FixedCost.is_active == True
    ).first()
    
    if existing_fixed:
        return RedirectResponse("/budget?error=duplicate_category", status_code=303)
    
    # Check if this category/subcategory already has a budget item
    existing = db.query(BudgetItem).filter(
        BudgetItem.user_id == user.id,
        BudgetItem.expense_category_id == expense_category_id,
        BudgetItem.expense_subcategory_id == subcat_id
    ).first()
    
    if existing:
        return RedirectResponse("/budget?error=duplicate_category", status_code=303)
    
    # Create new
    item = BudgetItem(
        user_id=user.id,
        expense_category_id=expense_category_id,
        expense_subcategory_id=subcat_id,
        use_tracked_average=use_tracked_average,
        specified_amount=specified_amount,
        tracking_period_months=tracking_period_months,
        category_type=category_type
    )
    db.add(item)
    
    db.commit()
    return RedirectResponse("/budget", status_code=303)


@router.get("/api/budget-item/{item_id}")
def get_budget_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    """Get a single budget item for editing."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    item = db.query(BudgetItem).filter(
        BudgetItem.id == item_id,
        BudgetItem.user_id == user.id
    ).first()
    
    if not item:
        return JSONResponse({"error": "Not found"}, status_code=404)
    
    # Get expense averages for this category
    expense_avgs = get_expense_averages_multi(db, user.id)
    
    # Get the correct averages based on whether a subcategory is selected
    if item.expense_subcategory_id:
        # Specific subcategory - use subcategory averages
        key = (item.expense_category_id, item.expense_subcategory_id)
        tracked_3mo = expense_avgs[3]["subcategory"].get(key, 0)
        tracked_6mo = expense_avgs[6]["subcategory"].get(key, 0)
        tracked_12mo = expense_avgs[12]["subcategory"].get(key, 0)
    elif item.expense_category_id:
        # Whole category (all subcategories) - use category averages
        tracked_3mo = expense_avgs[3]["category"].get(item.expense_category_id, 0)
        tracked_6mo = expense_avgs[6]["category"].get(item.expense_category_id, 0)
        tracked_12mo = expense_avgs[12]["category"].get(item.expense_category_id, 0)
    else:
        tracked_3mo = tracked_6mo = tracked_12mo = 0
    
    return JSONResponse({
        "id": item.id,
        "expense_category_id": item.expense_category_id,
        "expense_subcategory_id": item.expense_subcategory_id,
        "use_tracked_average": item.use_tracked_average,
        "specified_amount": item.specified_amount,
        "tracking_period_months": item.tracking_period_months or 3,
        "category_type": item.category_type,
        "tracked_3mo": tracked_3mo,
        "tracked_6mo": tracked_6mo,
        "tracked_12mo": tracked_12mo
    })


@router.post("/budget/item/update/{item_id}")
def update_budget_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    use_tracked_average: bool = Form(True),
    specified_amount: float = Form(0),
    tracking_period_months: int = Form(3),
    category_type: str = Form("need")
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    item = db.query(BudgetItem).filter(
        BudgetItem.id == item_id,
        BudgetItem.user_id == user.id
    ).first()
    
    if item:
        item.use_tracked_average = use_tracked_average
        item.specified_amount = specified_amount
        item.tracking_period_months = tracking_period_months
        item.category_type = category_type
        db.commit()
    
    return RedirectResponse("/budget", status_code=303)


@router.delete("/budget/item/{item_id}")
def delete_budget_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    item = db.query(BudgetItem).filter(
        BudgetItem.id == item_id,
        BudgetItem.user_id == user.id
    ).first()
    
    if item:
        db.delete(item)
        db.commit()
        return JSONResponse({"success": True})
    
    return JSONResponse({"error": "Not found"}, status_code=404)


@router.post("/budget/update-targets")
def update_budget_targets(
    request: Request,
    db: Session = Depends(get_db),
    needs_target: float = Form(50.0),
    wants_target: float = Form(30.0),
    savings_target: float = Form(20.0)
):
    """Update user's custom budget rule targets."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Clamp values to valid range
    user.budget_needs_target = max(0, min(100, needs_target))
    user.budget_wants_target = max(0, min(100, wants_target))
    user.budget_savings_target = max(0, min(100, savings_target))
    
    db.commit()
    return RedirectResponse("/budget", status_code=303)


@router.get("/api/budget/rolling-averages")
def get_rolling_averages_api(
    request: Request, 
    db: Session = Depends(get_db),
    category_id: int = Query(None),
    subcategory_id: int = Query(None)
):
    """API endpoint to get rolling averages for a category/subcategory combination."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    if not category_id:
        return JSONResponse({"tracked_3mo": 0, "tracked_6mo": 0, "tracked_12mo": 0})
    
    # Get expense averages
    expense_avgs = get_expense_averages_multi(db, user.id)
    
    # Get the correct averages based on whether a subcategory is selected
    if subcategory_id:
        # Specific subcategory - use subcategory averages
        key = (category_id, subcategory_id)
        tracked_3mo = expense_avgs[3]["subcategory"].get(key, 0)
        tracked_6mo = expense_avgs[6]["subcategory"].get(key, 0)
        tracked_12mo = expense_avgs[12]["subcategory"].get(key, 0)
    else:
        # Whole category (all subcategories) - use category averages
        tracked_3mo = expense_avgs[3]["category"].get(category_id, 0)
        tracked_6mo = expense_avgs[6]["category"].get(category_id, 0)
        tracked_12mo = expense_avgs[12]["category"].get(category_id, 0)
    
    return JSONResponse({
        "tracked_3mo": tracked_3mo,
        "tracked_6mo": tracked_6mo,
        "tracked_12mo": tracked_12mo
    })


@router.get("/api/budget/summary")
def get_budget_summary_api(request: Request, db: Session = Depends(get_db)):
    """API endpoint to get budget summary data."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    income_data = db.query(IncomeTaxes).filter(IncomeTaxes.user_id == user.id).first()
    summary = calculate_budget_summary(db, user.id, income_data)
    
    # Convert to JSON-serializable format
    return JSONResponse({
        "gross_monthly": summary["gross_monthly"],
        "net_monthly": summary["net_monthly"],
        "total_retirement_monthly": summary["total_retirement_monthly"],
        "total_fixed_monthly": summary["total_fixed_monthly"],
        "total_variable_monthly": summary["total_variable_monthly"],
        "total_needs": summary["total_needs"],
        "total_wants": summary["total_wants"],
        "total_savings": summary["total_savings"],
        "total_debt": summary["total_debt"],
        "leftover": summary["leftover"],
        "needs_pct": summary["needs_pct"],
        "wants_pct": summary["wants_pct"],
        "savings_pct": summary["savings_pct"],
        "debt_pct": summary["debt_pct"]
    })


# ===== SUBSCRIPTION/UTILITY TRACKING =====

UTILITY_TYPES = [
    ("subscription", "Subscription"),
    ("utility", "Utility"),
    ("service", "Service"),
]


def get_subscription_stats(db: Session, user_id: int) -> dict:
    """Calculate statistics for subscriptions/utilities."""
    subscriptions = db.query(SubscriptionUtility).filter(
        SubscriptionUtility.user_id == user_id,
        SubscriptionUtility.is_active == True
    ).all()
    
    today = date.today()
    one_month_ago = today - timedelta(days=30)
    three_months_ago = today - timedelta(days=90)
    one_year_ago = today - timedelta(days=365)
    
    results = []
    for sub in subscriptions:
        # Get all payments
        payments = sorted(sub.payments, key=lambda p: p.payment_date, reverse=True)
        
        # Calculate averages
        payments_1m = [p for p in payments if p.payment_date >= one_month_ago]
        payments_3m = [p for p in payments if p.payment_date >= three_months_ago]
        payments_12m = [p for p in payments if p.payment_date >= one_year_ago]
        
        avg_1m = sum(p.amount for p in payments_1m) if payments_1m else 0
        avg_3m = sum(p.amount for p in payments_3m) / 3 if payments_3m else 0
        avg_12m = sum(p.amount for p in payments_12m) / 12 if payments_12m else 0
        
        # Monthly trend (compare last 3 months to previous 3 months)
        six_months_ago = today - timedelta(days=180)
        payments_prev_3m = [p for p in payments if three_months_ago > p.payment_date >= six_months_ago]
        current_avg = avg_3m
        prev_avg = sum(p.amount for p in payments_prev_3m) / 3 if payments_prev_3m else 0
        trend = ((current_avg - prev_avg) / prev_avg * 100) if prev_avg > 0 else 0
        
        # Serialize last payment for JSON compatibility
        last_payment_data = None
        if payments:
            last_payment_data = {
                "id": payments[0].id,
                "amount": payments[0].amount,
                "date": payments[0].payment_date.isoformat(),
                "notes": payments[0].notes
            }
        
        # Serialize all payments for charts
        all_payments_data = [{
            "id": p.id,
            "amount": p.amount,
            "payment_date": p.payment_date.isoformat(),
            "notes": p.notes
        } for p in payments]
        
        results.append({
            "id": sub.id,
            "name": sub.name,
            "utility_type": sub.utility_type,
            "category_type": sub.category_type,
            "is_active": sub.is_active,
            "notes": sub.notes,
            "last_payment": last_payment_data,
            "payments": all_payments_data,  # Full payments list for charts
            "payment_count": len(payments),
            "total_1m": avg_1m,
            "avg_3m": avg_3m,
            "avg_12m": avg_12m,
            "trend_pct": trend
        })
    
    return {
        "subscriptions": results,
        "total_monthly": sum(r["avg_3m"] for r in results),
        "count_active": len([r for r in results if r["is_active"]])
    }


@router.get("/api/subscriptions")
def get_subscriptions_api(request: Request, db: Session = Depends(get_db)):
    """Get all subscriptions/utilities for current user."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    stats = get_subscription_stats(db, user.id)
    
    # Serialize for JSON
    serialized = []
    for sub in stats["subscriptions"]:
        serialized.append({
            "id": sub["id"],
            "name": sub["name"],
            "utility_type": sub["utility_type"],
            "category_type": sub["category_type"],
            "is_active": sub["is_active"],
            "notes": sub["notes"],
            "last_payment_date": sub["last_payment"].payment_date.isoformat() if sub["last_payment"] else None,
            "last_payment_amount": sub["last_payment"].amount if sub["last_payment"] else None,
            "payment_count": sub["payment_count"],
            "total_1m": sub["total_1m"],
            "avg_3m": sub["avg_3m"],
            "avg_12m": sub["avg_12m"],
            "trend_pct": sub["trend_pct"]
        })
    
    return JSONResponse({
        "subscriptions": serialized,
        "total_monthly": stats["total_monthly"],
        "count_active": stats["count_active"]
    })


@router.post("/budget/subscription/add")
def add_subscription(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    utility_type: str = Form("subscription"),
    category_type: str = Form("need"),
    notes: str = Form(None),
    initial_amount: float = Form(None),
    initial_date: str = Form(None),
    add_to_budget: bool = Form(True),
    tracking_period_months: int = Form(6)
):
    """Add a new subscription/utility to track."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    subscription = SubscriptionUtility(
        user_id=user.id,
        name=name.strip(),
        utility_type=utility_type,
        category_type=category_type,
        notes=notes.strip() if notes else None,
        is_active=True
    )
    db.add(subscription)
    db.flush()  # Get the ID
    
    # Add initial payment if provided
    if initial_amount and initial_date:
        from datetime import datetime
        payment = SubscriptionPayment(
            subscription_id=subscription.id,
            amount=initial_amount,
            payment_date=datetime.strptime(initial_date, "%Y-%m-%d").date()
        )
        db.add(payment)
    
    # Also add to budget as a variable expense (BudgetItem) if requested
    # This uses tracked average from the subscription payments
    if add_to_budget:
        # Find or create an expense category for subscriptions/utilities
        sub_category_name = f"Subscriptions & Utilities"
        exp_category = db.query(ExpenseCategory).filter(
            ExpenseCategory.user_id == user.id,
            ExpenseCategory.name == sub_category_name
        ).first()
        
        if not exp_category:
            exp_category = ExpenseCategory(user_id=user.id, name=sub_category_name)
            db.add(exp_category)
            db.flush()
        
        # Create a subcategory for this specific subscription
        subcategory = SubCategory(
            category_id=exp_category.id,
            name=name.strip()
        )
        db.add(subcategory)
        db.flush()
        
        # Link the subscription to this category/subcategory for tracking
        subscription.expense_category_id = exp_category.id
        subscription.expense_subcategory_id = subcategory.id
        
        # Create budget item using tracked average
        budget_item = BudgetItem(
            user_id=user.id,
            expense_category_id=exp_category.id,
            expense_subcategory_id=subcategory.id,
            use_tracked_average=True,
            specified_amount=initial_amount if initial_amount else 0,
            tracking_period_months=tracking_period_months,
            category_type=category_type
        )
        db.add(budget_item)
    
    db.commit()
    return RedirectResponse("/budget?tab=subscriptions", status_code=303)


@router.post("/budget/subscription/payment/add")
def add_subscription_payment(
    request: Request,
    db: Session = Depends(get_db),
    subscription_id: int = Form(...),
    amount: float = Form(...),
    payment_date: str = Form(...),
    notes: str = Form(None)
):
    """Add a payment record to a subscription."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Verify subscription belongs to user
    subscription = db.query(SubscriptionUtility).filter(
        SubscriptionUtility.id == subscription_id,
        SubscriptionUtility.user_id == user.id
    ).first()
    
    if not subscription:
        return RedirectResponse("/budget?tab=subscriptions&error=not_found", status_code=303)
    
    from datetime import datetime
    payment = SubscriptionPayment(
        subscription_id=subscription_id,
        amount=amount,
        payment_date=datetime.strptime(payment_date, "%Y-%m-%d").date(),
        notes=notes.strip() if notes else None
    )
    db.add(payment)
    db.commit()
    
    return RedirectResponse("/budget?tab=subscriptions", status_code=303)


@router.get("/api/subscription/{sub_id}")
def get_subscription_detail(sub_id: int, request: Request, db: Session = Depends(get_db)):
    """Get detailed subscription info with payment history."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    subscription = db.query(SubscriptionUtility).filter(
        SubscriptionUtility.id == sub_id,
        SubscriptionUtility.user_id == user.id
    ).first()
    
    if not subscription:
        return JSONResponse({"error": "Not found"}, status_code=404)
    
    payments = sorted(subscription.payments, key=lambda p: p.payment_date, reverse=True)
    
    # Group payments by month for chart
    from collections import defaultdict
    monthly_data = defaultdict(float)
    for p in payments:
        month_key = p.payment_date.strftime("%Y-%m")
        monthly_data[month_key] += p.amount
    
    sorted_months = sorted(monthly_data.keys())
    
    return JSONResponse({
        "id": subscription.id,
        "name": subscription.name,
        "utility_type": subscription.utility_type,
        "category_type": subscription.category_type,
        "is_active": subscription.is_active,
        "notes": subscription.notes,
        "payments": [
            {
                "id": p.id,
                "amount": p.amount,
                "date": p.payment_date.isoformat(),
                "notes": p.notes
            }
            for p in payments[:50]  # Last 50 payments
        ],
        "monthly_chart": {
            "labels": sorted_months,
            "data": [monthly_data[m] for m in sorted_months]
        }
    })


@router.post("/budget/subscription/update/{sub_id}")
def update_subscription(
    sub_id: int,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    utility_type: str = Form("subscription"),
    category_type: str = Form("need"),
    notes: str = Form(None),
    is_active: bool = Form(True)
):
    """Update a subscription."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    subscription = db.query(SubscriptionUtility).filter(
        SubscriptionUtility.id == sub_id,
        SubscriptionUtility.user_id == user.id
    ).first()
    
    if not subscription:
        return RedirectResponse("/budget?tab=subscriptions", status_code=303)
    
    subscription.name = name.strip()
    subscription.utility_type = utility_type
    subscription.category_type = category_type
    subscription.notes = notes.strip() if notes else None
    subscription.is_active = is_active
    
    db.commit()
    return RedirectResponse("/budget?tab=subscriptions", status_code=303)


@router.delete("/budget/subscription/{sub_id}")
def delete_subscription(sub_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a subscription and all its payments."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    subscription = db.query(SubscriptionUtility).filter(
        SubscriptionUtility.id == sub_id,
        SubscriptionUtility.user_id == user.id
    ).first()
    
    if subscription:
        db.delete(subscription)
        db.commit()
        return JSONResponse({"success": True})
    
    return JSONResponse({"error": "Not found"}, status_code=404)


@router.delete("/budget/subscription/payment/{payment_id}")
def delete_subscription_payment(payment_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a specific payment."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    payment = db.query(SubscriptionPayment).filter(SubscriptionPayment.id == payment_id).first()
    
    if payment:
        # Verify user owns the subscription
        subscription = db.query(SubscriptionUtility).filter(
            SubscriptionUtility.id == payment.subscription_id,
            SubscriptionUtility.user_id == user.id
        ).first()
        
        if subscription:
            db.delete(payment)
            db.commit()
            return JSONResponse({"success": True})
    
    return JSONResponse({"error": "Not found"}, status_code=404)


# ===== BUDGET IMPORT/EXPORT =====

@router.get("/budget/csv-export")
def export_budget_csv(request: Request, db: Session = Depends(get_db)):
    """Export all budget data as CSV."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row with all fields
    writer.writerow([
        "type",  # fixed_cost, budget_item, subscription, subscription_payment
        "name",
        "amount",
        "frequency",
        "category_type",
        "is_active",
        "amount_mode",
        "tracking_period_months",
        "expense_category",
        "expense_subcategory",
        "use_tracked_average",
        "utility_type",  # For subscriptions
        "notes",
        "payment_date",  # For subscription payments
        "parent_subscription"  # Name of subscription for payments
    ])
    
    # Export fixed costs
    fixed_costs = db.query(FixedCost).filter(FixedCost.user_id == user.id).all()
    for cost in fixed_costs:
        # Get linked category names
        exp_cat = ""
        exp_subcat = ""
        if cost.expense_category_id:
            cat = db.query(ExpenseCategory).filter(ExpenseCategory.id == cost.expense_category_id).first()
            exp_cat = cat.name if cat else ""
        if cost.expense_subcategory_id:
            subcat = db.query(SubCategory).filter(SubCategory.id == cost.expense_subcategory_id).first()
            exp_subcat = subcat.name if subcat else ""
        
        writer.writerow([
            "fixed_cost",
            cost.name,
            cost.amount,
            cost.frequency,
            cost.category_type,
            cost.is_active,
            cost.amount_mode or "fixed",
            cost.tracking_period_months or 3,
            exp_cat,
            exp_subcat,
            "",  # use_tracked_average (not used for fixed costs)
            "",  # utility_type
            "",  # notes
            "",  # payment_date
            ""   # parent_subscription
        ])
    
    # Export budget items
    budget_items = db.query(BudgetItem).filter(BudgetItem.user_id == user.id).all()
    for item in budget_items:
        exp_cat = ""
        exp_subcat = ""
        if item.expense_category_id:
            cat = db.query(ExpenseCategory).filter(ExpenseCategory.id == item.expense_category_id).first()
            exp_cat = cat.name if cat else ""
        if item.expense_subcategory_id:
            subcat = db.query(SubCategory).filter(SubCategory.id == item.expense_subcategory_id).first()
            exp_subcat = subcat.name if subcat else ""
        
        writer.writerow([
            "budget_item",
            "",  # name (not used for budget items)
            item.specified_amount or 0,
            "",  # frequency
            item.category_type,
            "",  # is_active
            "",  # amount_mode
            item.tracking_period_months or 3,
            exp_cat,
            exp_subcat,
            item.use_tracked_average,
            "",  # utility_type
            "",  # notes
            "",  # payment_date
            ""   # parent_subscription
        ])
    
    # Export subscriptions
    subscriptions = db.query(SubscriptionUtility).filter(SubscriptionUtility.user_id == user.id).all()
    for sub in subscriptions:
        writer.writerow([
            "subscription",
            sub.name,
            "",  # amount (tracked via payments)
            "",  # frequency
            sub.category_type,
            sub.is_active,
            "",  # amount_mode
            "",  # tracking_period_months
            "",  # expense_category
            "",  # expense_subcategory
            "",  # use_tracked_average
            sub.utility_type,
            sub.notes or "",
            "",  # payment_date
            ""   # parent_subscription
        ])
        
        # Export payments for this subscription
        for payment in sub.payments:
            writer.writerow([
                "subscription_payment",
                "",  # name
                payment.amount,
                "",  # frequency
                "",  # category_type
                "",  # is_active
                "",  # amount_mode
                "",  # tracking_period_months
                "",  # expense_category
                "",  # expense_subcategory
                "",  # use_tracked_average
                "",  # utility_type
                payment.notes or "",
                payment.payment_date.isoformat(),
                sub.name  # parent_subscription
            ])
    
    output.seek(0)
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=moneyflow_budget_{date.today().isoformat()}.csv"
        }
    )


@router.get("/budget/csv-template")
def get_budget_csv_template(request: Request):
    """Download a template CSV for budget import."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        "type",
        "name",
        "amount",
        "frequency",
        "category_type",
        "is_active",
        "amount_mode",
        "tracking_period_months",
        "expense_category",
        "expense_subcategory",
        "use_tracked_average",
        "utility_type",
        "notes",
        "payment_date",
        "parent_subscription"
    ])
    
    # Example rows
    writer.writerow([
        "fixed_cost",
        "Rent",
        "1500",
        "monthly",
        "need",
        "TRUE",
        "fixed",
        "3",
        "",
        "",
        "",
        "",
        "",
        "",
        ""
    ])
    writer.writerow([
        "fixed_cost",
        "Electric Bill",
        "150",
        "monthly",
        "need",
        "TRUE",
        "tracked",
        "3",
        "Utilities",
        "Electric",
        "",
        "",
        "",
        "",
        ""
    ])
    writer.writerow([
        "budget_item",
        "",
        "400",
        "",
        "need",
        "",
        "",
        "3",
        "Groceries",
        "",
        "TRUE",
        "",
        "",
        "",
        ""
    ])
    writer.writerow([
        "subscription",
        "Netflix",
        "",
        "",
        "want",
        "TRUE",
        "",
        "",
        "",
        "",
        "",
        "subscription",
        "Streaming service",
        "",
        ""
    ])
    writer.writerow([
        "subscription_payment",
        "",
        "15.99",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "December payment",
        "2024-12-01",
        "Netflix"
    ])
    
    output.seek(0)
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=moneyflow_budget_template.csv"
        }
    )


@router.post("/budget/csv-import")
async def import_budget_csv(
    request: Request,
    db: Session = Depends(get_db),
    csv_file: UploadFile = File(...)
):
    """Import budget data from CSV."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    try:
        content = await csv_file.read()
        decoded = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded))
        
        imported = {"fixed_costs": 0, "budget_items": 0, "subscriptions": 0, "payments": 0}
        errors = []
        subscription_map = {}  # Map subscription names to IDs for payment linking
        
        # First pass: collect existing subscriptions
        existing_subs = db.query(SubscriptionUtility).filter(SubscriptionUtility.user_id == user.id).all()
        for sub in existing_subs:
            subscription_map[sub.name.lower()] = sub.id
        
        for row_num, row in enumerate(reader, start=2):
            try:
                row_type = row.get("type", "").strip().lower()
                
                if row_type == "fixed_cost":
                    # Get or create linked expense category
                    exp_cat_id = None
                    exp_subcat_id = None
                    exp_cat_name = row.get("expense_category", "").strip()
                    exp_subcat_name = row.get("expense_subcategory", "").strip()
                    
                    if exp_cat_name:
                        cat = db.query(ExpenseCategory).filter(
                            ExpenseCategory.user_id == user.id,
                            ExpenseCategory.name == exp_cat_name
                        ).first()
                        if cat:
                            exp_cat_id = cat.id
                            if exp_subcat_name:
                                subcat = db.query(SubCategory).filter(
                                    SubCategory.category_id == cat.id,
                                    SubCategory.name == exp_subcat_name
                                ).first()
                                if subcat:
                                    exp_subcat_id = subcat.id
                    
                    cost = FixedCost(
                        user_id=user.id,
                        name=row.get("name", "Imported Cost").strip(),
                        amount=float(row.get("amount", 0) or 0),
                        frequency=row.get("frequency", "monthly").strip() or "monthly",
                        category_type=row.get("category_type", "need").strip() or "need",
                        is_active=row.get("is_active", "TRUE").strip().upper() in ("TRUE", "1", "YES"),
                        amount_mode=row.get("amount_mode", "fixed").strip() or "fixed",
                        tracking_period_months=int(row.get("tracking_period_months", 3) or 3),
                        expense_category_id=exp_cat_id,
                        expense_subcategory_id=exp_subcat_id
                    )
                    db.add(cost)
                    imported["fixed_costs"] += 1
                    
                elif row_type == "budget_item":
                    # Get linked expense category
                    exp_cat_id = None
                    exp_subcat_id = None
                    exp_cat_name = row.get("expense_category", "").strip()
                    exp_subcat_name = row.get("expense_subcategory", "").strip()
                    
                    if exp_cat_name:
                        cat = db.query(ExpenseCategory).filter(
                            ExpenseCategory.user_id == user.id,
                            ExpenseCategory.name == exp_cat_name
                        ).first()
                        if cat:
                            exp_cat_id = cat.id
                            if exp_subcat_name:
                                subcat = db.query(SubCategory).filter(
                                    SubCategory.category_id == cat.id,
                                    SubCategory.name == exp_subcat_name
                                ).first()
                                if subcat:
                                    exp_subcat_id = subcat.id
                    
                    if exp_cat_id:  # Only create if we have a valid category
                        item = BudgetItem(
                            user_id=user.id,
                            expense_category_id=exp_cat_id,
                            expense_subcategory_id=exp_subcat_id,
                            specified_amount=float(row.get("amount", 0) or 0),
                            category_type=row.get("category_type", "need").strip() or "need",
                            use_tracked_average=row.get("use_tracked_average", "FALSE").strip().upper() in ("TRUE", "1", "YES"),
                            tracking_period_months=int(row.get("tracking_period_months", 3) or 3)
                        )
                        db.add(item)
                        imported["budget_items"] += 1
                    
                elif row_type == "subscription":
                    sub = SubscriptionUtility(
                        user_id=user.id,
                        name=row.get("name", "Imported Subscription").strip(),
                        utility_type=row.get("utility_type", "subscription").strip() or "subscription",
                        category_type=row.get("category_type", "need").strip() or "need",
                        is_active=row.get("is_active", "TRUE").strip().upper() in ("TRUE", "1", "YES"),
                        notes=row.get("notes", "").strip() or None
                    )
                    db.add(sub)
                    db.flush()  # Get ID
                    subscription_map[sub.name.lower()] = sub.id
                    imported["subscriptions"] += 1
                    
                elif row_type == "subscription_payment":
                    parent_name = row.get("parent_subscription", "").strip().lower()
                    if parent_name and parent_name in subscription_map:
                        payment_date_str = row.get("payment_date", "").strip()
                        if payment_date_str:
                            payment = SubscriptionPayment(
                                subscription_id=subscription_map[parent_name],
                                amount=float(row.get("amount", 0) or 0),
                                payment_date=datetime.strptime(payment_date_str, "%Y-%m-%d").date(),
                                notes=row.get("notes", "").strip() or None
                            )
                            db.add(payment)
                            imported["payments"] += 1
                    else:
                        errors.append(f"Row {row_num}: Subscription '{parent_name}' not found for payment")
                        
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        db.commit()
        
        # Build success message
        msg_parts = []
        if imported["fixed_costs"]: msg_parts.append(f"{imported['fixed_costs']} fixed costs")
        if imported["budget_items"]: msg_parts.append(f"{imported['budget_items']} budget items")
        if imported["subscriptions"]: msg_parts.append(f"{imported['subscriptions']} subscriptions")
        if imported["payments"]: msg_parts.append(f"{imported['payments']} payments")
        
        success_msg = "Imported: " + ", ".join(msg_parts) if msg_parts else "No data imported"
        if errors:
            success_msg += f" ({len(errors)} errors)"
        
        return RedirectResponse(f"/budget?success={success_msg.replace(' ', '+')}", status_code=303)
        
    except Exception as e:
        logger.error(f"Budget import error: {e}")
        return RedirectResponse(f"/budget?error=Import+failed:+{str(e)[:50]}", status_code=303)

