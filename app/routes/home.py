"""
Home/Dashboard route for MoneyFlow application.

This module handles the main dashboard view, including:
- Money flow Sankey chart visualization
- Spending trends and analytics
- Monthly summary statistics
"""

from datetime import date, timedelta
from collections import defaultdict

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.db import get_db
from app.models.user import User
from app.models.income_taxes import IncomeTaxes
from app.models.expense import Expense, Category as ExpenseCategory, SubCategory
from app.models.budget import FixedCost, BudgetItem
from app.models.networth import Account
from app.routes.income_taxes import calculate_taxes
from app.routes.budget import calculate_budget_summary
from app.routes.tools import calculate_net_worth_summary
from app.logging_config import get_logger
import base64

# Module logger for home/dashboard operations
logger = get_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_profile_picture_data(user):
    """
    Get base64 encoded profile picture data for templates.
    
    Args:
        user: User model instance
        
    Returns:
        Tuple of (base64_data, mime_type) or (None, None) if no picture
    """
    if user.profile_picture and user.profile_picture_type:
        return base64.b64encode(user.profile_picture).decode('utf-8'), user.profile_picture_type
    return None, None


def generate_sankey_data(summary, income_data, include_details=False):
    """
    Generate Sankey chart data from budget summary.
    
    Creates a flow diagram showing how income flows through taxes,
    deductions, and various expense categories.
    
    Args:
        summary: Budget summary dictionary from calculate_budget_summary
        income_data: IncomeTaxes model instance
        include_details: If True, includes detailed breakdown to individual items
        
    Returns:
        List of [from, to, amount] triples for Sankey chart
    """
    logger.debug(f"Generating Sankey chart data (details={include_details})")
    
    if not summary or not income_data:
        logger.warning("No summary or income data available for Sankey chart")
        return []
    
    sankey_data = []
    gross_monthly = summary.get("gross_monthly", 0)
    
    if gross_monthly <= 0:
        logger.warning("Gross monthly income is zero or negative")
        return []
    
    # Income sources to Gross Income
    sankey_data.append(["Salary", "Gross Income", round(gross_monthly, 0)])
    
    # Gross Income breakdown
    income_calc = summary.get("income", {}) or {}
    if income_calc:
        # Taxes
        total_taxes = income_calc.get("total_taxes", 0) / 12
        if total_taxes > 0:
            sankey_data.append(["Gross Income", "Taxes", round(total_taxes, 0)])
            
            # Break down taxes (always show this level)
            federal = income_calc.get("total_federal_tax", 0) / 12
            state = income_calc.get("mo_state_tax", 0) / 12
            fica = income_calc.get("total_fica", 0) / 12
            
            if federal > 0:
                sankey_data.append(["Taxes", "Federal Tax", round(federal, 0)])
            if state > 0:
                sankey_data.append(["Taxes", "State Tax", round(state, 0)])
            if fica > 0:
                sankey_data.append(["Taxes", "FICA", round(fica, 0)])
        
        # Pretax deductions
        pretax_deductions = income_calc.get("pretax_deductions_annual", 0) / 12
        if pretax_deductions > 0:
            sankey_data.append(["Gross Income", "Pretax Benefits", round(pretax_deductions, 0)])
        
        # Retirement contributions
        retirement = summary.get("total_retirement_monthly", 0)
        if retirement > 0:
            sankey_data.append(["Gross Income", "Retirement", round(retirement, 0)])
    
    # Net income to categories
    net_monthly = summary.get("net_monthly", 0)
    if net_monthly > 0:
        sankey_data.append(["Gross Income", "Net Income", round(net_monthly, 0)])
        
        # Fixed costs by type
        fixed_by_type = summary.get("fixed_costs_by_type", {})
        variable_by_type = summary.get("variable_costs_by_type", {})
        
        needs = fixed_by_type.get("need", 0) + variable_by_type.get("need", 0)
        wants = fixed_by_type.get("want", 0) + variable_by_type.get("want", 0)
        savings = fixed_by_type.get("savings", 0)
        debt = fixed_by_type.get("debt", 0)
        
        if needs > 0:
            sankey_data.append(["Net Income", "Needs", round(needs, 0)])
        if wants > 0:
            sankey_data.append(["Net Income", "Wants", round(wants, 0)])
        if savings > 0:
            sankey_data.append(["Net Income", "Savings", round(savings, 0)])
        if debt > 0:
            sankey_data.append(["Net Income", "Debt Payments", round(debt, 0)])
        
        # Leftover
        leftover = summary.get("leftover", 0)
        if leftover > 0:
            sankey_data.append(["Net Income", "Unallocated", round(leftover, 0)])
        
        # Only include detailed breakdown if requested
        if include_details:
            # Break down fixed costs into specific items
            fixed_details = summary.get("fixed_costs_details", [])
            # Sort by monthly amount and get top items
            sorted_details = sorted(fixed_details, key=lambda x: x.get("monthly_amount", 0), reverse=True)
            
            for cost in sorted_details[:12]:  # Limit to top 12 when showing details
                monthly = cost.get("monthly_amount", 0)
                if monthly >= 25:  # Lower threshold when showing details
                    cost_type = cost.get("category_type", "need")
                    parent = {
                        "need": "Needs",
                        "want": "Wants", 
                        "savings": "Savings",
                        "debt": "Debt Payments"
                    }.get(cost_type, "Needs")
                    name = cost.get("name", "Other")[:20]  # Truncate long names
                    sankey_data.append([parent, name, round(monthly, 0)])
    
    logger.info(f"Generated Sankey data with {len(sankey_data)} flows")
    return sankey_data


def calculate_spending_trends(db: Session, user_id: int):
    """
    Calculate spending trends for the dashboard.
    
    Analyzes expense data to show:
    - Top spending categories with month-over-month change
    - Top subcategories
    - Monthly spending totals for trend chart
    - Category breakdown for pie chart
    
    Args:
        db: Database session
        user_id: Current user's ID
        
    Returns:
        Dictionary with trend data or None if insufficient data
    """
    logger.debug(f"Calculating spending trends for user {user_id}")
    
    today = date.today()
    current_month_start = today.replace(day=1)
    
    # Get expenses for last 6 months
    six_months_ago = today - timedelta(days=180)
    
    expenses = db.query(Expense).filter(
        Expense.user_id == user_id,
        Expense.expense_date >= six_months_ago
    ).all()
    
    if not expenses:
        logger.info("No expenses found for trends calculation")
        return None
    
    # Get category and subcategory names
    categories = {c.id: c.name for c in db.query(ExpenseCategory).filter(ExpenseCategory.user_id == user_id).all()}
    # SubCategory is linked to Category via category_id, so join through Category to filter by user
    subcategories = {
        s.id: s.name 
        for s in db.query(SubCategory).join(ExpenseCategory).filter(ExpenseCategory.user_id == user_id).all()
    }
    
    # Current month totals by category
    current_month_by_cat = defaultdict(float)
    current_month_by_subcat = defaultdict(float)
    
    # Previous month totals for comparison
    prev_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    prev_month_by_cat = defaultdict(float)
    prev_month_by_subcat = defaultdict(float)
    
    # Monthly totals for bar chart
    monthly_totals = defaultdict(float)
    
    for expense in expenses:
        exp_date = expense.expense_date
        month_key = exp_date.strftime("%b %Y")
        monthly_totals[month_key] += expense.amount
        
        cat_name = categories.get(expense.category_id, "Other")
        subcat_name = subcategories.get(expense.subcategory_id, "")
        
        # Current month
        if exp_date >= current_month_start:
            current_month_by_cat[cat_name] += expense.amount
            if subcat_name:
                current_month_by_subcat[f"{cat_name}: {subcat_name}"] += expense.amount
        
        # Previous month
        elif exp_date >= prev_month_start and exp_date < current_month_start:
            prev_month_by_cat[cat_name] += expense.amount
            if subcat_name:
                prev_month_by_subcat[f"{cat_name}: {subcat_name}"] += expense.amount
    
    # Calculate top categories with change percentage
    top_categories = []
    for cat, amount in sorted(current_month_by_cat.items(), key=lambda x: x[1], reverse=True)[:10]:
        prev_amount = prev_month_by_cat.get(cat, 0)
        change = ((amount - prev_amount) / prev_amount * 100) if prev_amount > 0 else 0
        top_categories.append({
            "name": cat,
            "amount": amount,
            "change": change
        })
    
    # Calculate top subcategories
    top_subcategories = []
    for subcat, amount in sorted(current_month_by_subcat.items(), key=lambda x: x[1], reverse=True)[:10]:
        prev_amount = prev_month_by_subcat.get(subcat, 0)
        change = ((amount - prev_amount) / prev_amount * 100) if prev_amount > 0 else 0
        top_subcategories.append({
            "name": subcat,
            "amount": amount,
            "change": change
        })
    
    # Build monthly trend data (last 6 months)
    months = []
    totals = []
    for i in range(5, -1, -1):
        month_date = today - timedelta(days=i*30)
        month_key = month_date.strftime("%b %Y")
        months.append(month_date.strftime("%b"))
        totals.append(round(monthly_totals.get(month_key, 0), 0))
    
    # Category data for pie chart
    category_names = list(current_month_by_cat.keys())[:10]
    category_amounts = [round(current_month_by_cat[name], 0) for name in category_names]
    
    logger.info(f"Calculated trends: {len(top_categories)} categories, {len(top_subcategories)} subcategories")
    
    return {
        "top_categories": top_categories,
        "top_subcategories": top_subcategories,
        "months": months,
        "monthly_totals": totals,
        "category_names": category_names,
        "category_amounts": category_amounts
    }


@router.get("/home")
def home(request: Request, db: Session = Depends(get_db)):
    """
    Render the main dashboard/home page.
    
    Displays:
    - Money flow Sankey chart
    - Monthly financial summary
    - Spending trends and analytics
    - Quick action links
    """
    logger.info("Loading home page")
    
    # Authenticate user
    username = request.cookies.get("username")
    if not username:
        logger.debug("No username cookie, redirecting to login")
        return RedirectResponse("/login")
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning(f"User not found for username: {username}")
        return RedirectResponse("/login")
    
    logger.debug(f"Authenticated user: {user.username}")
    
    # Check if user needs to complete tutorial
    if not user.tutorial_completed:
        logger.info(f"Redirecting user {user.username} to tutorial")
        return RedirectResponse("/tutorial")
    
    profile_picture_b64, profile_picture_type = get_profile_picture_data(user)
    
    # Get income and budget data for Sankey chart
    income_data = db.query(IncomeTaxes).filter(IncomeTaxes.user_id == user.id).first()
    summary = None
    sankey_data = []
    
    sankey_data_detailed = []
    
    if income_data:
        logger.debug("Calculating budget summary")
        summary = calculate_budget_summary(db, user.id, income_data)
        sankey_data = generate_sankey_data(summary, income_data, include_details=False)
        sankey_data_detailed = generate_sankey_data(summary, income_data, include_details=True)
    else:
        logger.info("No income data found for user")
    
    # Get spending trends
    spending_trends = calculate_spending_trends(db, user.id)
    
    # Get net worth summary for dashboard
    networth_accounts = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_active == True
    ).all()
    
    networth_summary = None
    if networth_accounts:
        networth_summary = calculate_net_worth_summary(networth_accounts)
        logger.debug(f"Net worth summary: {networth_summary.get('net_worth', 0)}")
    
    return templates.TemplateResponse("home.html", {
        "request": request,
        "title": "Dashboard",
        "user": user,
        "profile_picture_b64": profile_picture_b64,
        "profile_picture_type": profile_picture_type,
        "dark_mode": user.dark_mode,
        "summary": summary,
        "sankey_data": sankey_data,
        "sankey_data_detailed": sankey_data_detailed,
        "spending_trends": spending_trends,
        "networth_summary": networth_summary
    })
