"""
Expense tracking routes for MoneyFlow application.

This module handles all expense-related functionality including:
- Adding, editing, and deleting individual expenses
- Category and subcategory management
- Expense statistics and visualizations
- CSV bulk import/export
- Recurring expense tracking

Key Features:
- Flexible date filtering (1 month, 3 months, 6 months, 1 year, all time)
- Category-based organization with subcategories
- Support for recurring expenses with various frequencies
- Statistical analysis including trends and averages
- Visual charts (stacked bar, category breakdowns)

Routes:
    GET  /expenses              - Main expenses page with visualizations
    POST /expenses/add          - Add new expense
    POST /expenses/update/<id>  - Update existing expense
    DELETE /expenses/<id>       - Delete expense
    POST /expenses/category/add - Add new category
    POST /expenses/subcategory/add - Add new subcategory
    GET  /api/subcategories/<id>   - Get subcategories for a category
    POST /expenses/upload       - Bulk upload expenses via CSV
    GET  /expenses/template     - Download CSV template
"""

from fastapi import APIRouter, Request, Form, Depends, Query, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import date, datetime, timedelta
from typing import Optional, List
from app.db import get_db
from app.models.user import User
from app.models.expense import Category, SubCategory, Expense, Vendor
from app.logging_config import get_logger
from calendar import monthrange
import base64
import csv
import io

# Module logger for expense tracking operations
logger = get_logger(__name__)

# Router and template configuration
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Lookback period options (in days)
LOOKBACK_PERIODS = {
    "1d": {"days": 1, "label": "1 Day"},
    "1w": {"days": 7, "label": "1 Week"},
    "1m": {"days": 30, "label": "1 Month"},
    "3m": {"days": 90, "label": "3 Months"},
    "6m": {"days": 180, "label": "6 Months"},
    "1y": {"days": 365, "label": "1 Year"},
    "all": {"days": None, "label": "All Time"}
}


def get_current_user(request: Request, db: Session):
    """Get the logged-in user from cookies."""
    username = request.cookies.get("username")
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()


def get_profile_picture_data(user):
    """Get base64 encoded profile picture data for templates."""
    if user and user.profile_picture and user.profile_picture_type:
        return base64.b64encode(user.profile_picture).decode('utf-8'), user.profile_picture_type
    return None, None


def get_expense_stats(db: Session, user_id: int, lookback: str = "1m", category_filters: Optional[List[int]] = None, vendor_filters: Optional[List[int]] = None):
    """Calculate expense statistics for visualizations with lookback period, category, and vendor filters."""
    today = date.today()
    
    # Determine date range
    lookback_info = LOOKBACK_PERIODS.get(lookback, LOOKBACK_PERIODS["all"])
    if lookback_info["days"]:
        start_date = today - timedelta(days=lookback_info["days"])
    else:
        start_date = None  # All time
    
    # Build query
    query = db.query(Expense).filter(Expense.user_id == user_id)
    if start_date:
        query = query.filter(Expense.expense_date >= start_date)
    if category_filters and len(category_filters) > 0:
        query = query.filter(Expense.category_id.in_(category_filters))
    if vendor_filters and len(vendor_filters) > 0:
        query = query.filter(Expense.vendor_id.in_(vendor_filters))
    
    expenses = query.order_by(Expense.expense_date).all()
    
    # Total in period
    total_in_period = sum(e.amount for e in expenses)
    
    # By category
    by_category = {}
    category_counts = {}
    category_id_map = {}  # Map category name to id for coloring
    for expense in expenses:
        # todo: fix expense summing by category
        cat_name = expense.category.name if expense.category else "Uncategorized"
        cat_id = expense.category_id if expense.category else 0
        by_category[cat_name] = by_category.get(cat_name, 0) + expense.amount
        category_counts[cat_name] = category_counts.get(cat_name, 0) + 1
        category_id_map[cat_name] = cat_id
    
    # Sort by amount descending
    by_category_sorted = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    
    # Calculate average per category
    category_averages = []
    for cat_name, total in by_category_sorted:
        count = category_counts.get(cat_name, 1)
        avg = total / count if count > 0 else 0
        category_averages.append({
            "name": cat_name,
            "total": total,
            "count": count,
            "average": avg,
            "category_id": category_id_map.get(cat_name, 0)
        })
    
    # Monthly trend by category (for stacked bar chart)
    num_months = min(12, max(1, (lookback_info["days"] or 365) // 30))
    monthly_by_category = {}  # {category_name: [{month, total}, ...]}
    months_list = []
    
    for i in range(num_months - 1, -1, -1):
        month_date = today - timedelta(days=i * 30)
        month_start = month_date.replace(day=1)
        _, last_day = monthrange(month_start.year, month_start.month)
        month_end = month_start.replace(day=last_day)
        month_label = month_start.strftime("%b '%y")
        months_list.append(month_label)
        
        # Get expenses for this month
        month_expenses = [e for e in expenses if month_start <= e.expense_date <= month_end]
        
        # Sum by category
        for expense in month_expenses:
            cat_name = expense.category.name if expense.category else "Uncategorized"
            if cat_name not in monthly_by_category:
                monthly_by_category[cat_name] = {}
            monthly_by_category[cat_name][month_label] = monthly_by_category[cat_name].get(month_label, 0) + expense.amount
    
    # Format for stacked bar chart
    stacked_data = []
    for cat_name in monthly_by_category:
        cat_data = {
            "category": cat_name,
            "category_id": category_id_map.get(cat_name, 0),
            "data": [monthly_by_category[cat_name].get(m, 0) for m in months_list]
        }
        stacked_data.append(cat_data)
    
    # Monthly totals (for simple line chart)
    monthly_totals = []
    for month_label in months_list:
        total = sum(monthly_by_category.get(cat, {}).get(month_label, 0) for cat in monthly_by_category)
        monthly_totals.append({"month": month_label, "total": total})
    
    # Scatter plot data (individual expenses over time by category)
    scatter_data = []
    for expense in expenses:
        cat_name = expense.category.name if expense.category else "Uncategorized"
        scatter_data.append({
            "date": expense.expense_date.isoformat(),
            "amount": expense.amount,
            "category": cat_name,
            "category_id": expense.category_id if expense.category else 0,
            "notes": expense.notes[:30] + "..." if expense.notes and len(expense.notes) > 30 else (expense.notes or "")
        })
    
    # Calculate overall average per expense
    overall_avg = total_in_period / len(expenses) if expenses else 0
    
    # Days in period for daily average
    days_in_period = lookback_info["days"] or (today - min(e.expense_date for e in expenses)).days + 1 if expenses else 1
    daily_avg = total_in_period / days_in_period if days_in_period > 0 else 0
    
    # Calculate months in period for monthly average
    if expenses:
        earliest_date = min(e.expense_date for e in expenses)
        latest_date = max(e.expense_date for e in expenses)
        months_in_period = max(1, ((latest_date.year - earliest_date.year) * 12 + 
                                   (latest_date.month - earliest_date.month) + 1))
    else:
        months_in_period = 1
    
    monthly_avg = total_in_period / months_in_period if months_in_period > 0 else 0
    
    # Subcategory breakdown
    subcategory_data = {}  # {(cat_name, subcat_name): {total, count}}
    for expense in expenses:
        cat_name = expense.category.name if expense.category else "Uncategorized"
        subcat_name = expense.subcategory.name if expense.subcategory else None
        key = (cat_name, subcat_name)
        if key not in subcategory_data:
            subcategory_data[key] = {"total": 0, "count": 0}
        subcategory_data[key]["total"] += expense.amount
        subcategory_data[key]["count"] += 1
    
    # Format subcategory data for chart (sorted by category then subcategory)
    subcategory_chart_data = []
    subcategory_stats_list = []
    
    for cat_name, _ in by_category_sorted:
        # Add category total first
        cat_total = by_category.get(cat_name, 0)
        cat_count = category_counts.get(cat_name, 0)
        cat_monthly_avg = cat_total / months_in_period if months_in_period > 0 else 0
        subcategory_stats_list.append({
            "name": cat_name,
            "total": cat_total,
            "count": cat_count,
            "monthly_avg": cat_monthly_avg,
            "is_subcategory": False
        })
        
        # Get subcategories for this category
        subcats = [(k, v) for k, v in subcategory_data.items() if k[0] == cat_name and k[1] is not None]
        subcats_sorted = sorted(subcats, key=lambda x: x[1]["total"], reverse=True)
        
        for (cat, subcat_name), data in subcats_sorted:
            subcat_monthly_avg = data["total"] / months_in_period if months_in_period > 0 else 0
            subcategory_chart_data.append({
                "label": f"{cat}: {subcat_name}",
                "total": data["total"],
                "category": cat
            })
            subcategory_stats_list.append({
                "name": subcat_name,
                "total": data["total"],
                "count": data["count"],
                "monthly_avg": subcat_monthly_avg,
                "is_subcategory": True
            })
    
    # Vendor statistics
    by_vendor = {}
    vendor_counts = {}
    for expense in expenses:
        vendor_name = expense.vendor.name if expense.vendor else "No Vendor"
        vendor_id = expense.vendor_id if expense.vendor else 0
        by_vendor[vendor_name] = by_vendor.get(vendor_name, 0) + expense.amount
        vendor_counts[vendor_name] = vendor_counts.get(vendor_name, 0) + 1
    
    # Sort vendors by amount descending
    by_vendor_sorted = sorted(by_vendor.items(), key=lambda x: x[1], reverse=True)
    
    # Calculate vendor statistics
    vendor_stats = []
    for vendor_name, total in by_vendor_sorted:
        count = vendor_counts.get(vendor_name, 1)
        avg = total / count if count > 0 else 0
        monthly_avg = total / months_in_period if months_in_period > 0 else 0
        vendor_stats.append({
            "name": vendor_name,
            "total": total,
            "count": count,
            "average": avg,
            "monthly_avg": monthly_avg,
            "percentage": (total / total_in_period * 100) if total_in_period > 0 else 0
        })
    
    return {
        "total_in_period": total_in_period,
        "total_spending": total_in_period,  # Alias for template
        "by_category": by_category_sorted,
        "category_averages": category_averages,
        "monthly_trend": monthly_totals,
        "months_list": months_list,
        "stacked_data": stacked_data,
        "scatter_data": scatter_data,
        "subcategory_chart_data": subcategory_chart_data,
        "subcategory_stats": subcategory_stats_list,
        "vendor_stats": vendor_stats,
        "by_vendor": by_vendor_sorted,
        "expense_count": len(expenses),
        "overall_avg": overall_avg,
        "daily_avg": daily_avg,
        "monthly_avg": monthly_avg,
        "months_in_period": months_in_period,
        "lookback": lookback,
        "lookback_label": lookback_info["label"]
    }


@router.get("/expenses")
def expenses_page(
    request: Request, 
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    show_all: bool = Query(False),
    lookback: str = Query("all"),
    categories_filter: str = Query(""),  # Comma-separated category IDs
    vendors_filter: str = Query("")  # Comma-separated vendor IDs
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Get user's categories with subcategories
    categories = db.query(Category).filter(Category.user_id == user.id).order_by(Category.name).all()
    
    # Get user's vendors
    vendors = db.query(Vendor).filter(Vendor.user_id == user.id).order_by(Vendor.name).all()
    
    # Parse category filters (comma-separated IDs)
    category_filters = []
    if categories_filter:
        try:
            category_filters = [int(c.strip()) for c in categories_filter.split(",") if c.strip()]
        except ValueError:
            category_filters = []
    
    # Parse vendor filters (comma-separated IDs)
    vendor_filters = []
    if vendors_filter:
        try:
            vendor_filters = [int(v.strip()) for v in vendors_filter.split(",") if v.strip()]
        except ValueError:
            vendor_filters = []
    
    # Get recent expenses
    per_page = 50 if show_all else 10
    offset = (page - 1) * per_page
    recent_expenses_query = db.query(Expense).filter(Expense.user_id == user.id)

    #Filter by lookback period
    today = date.today()
    lookback_info = LOOKBACK_PERIODS.get(lookback, LOOKBACK_PERIODS["all"])
    if lookback_info["days"]:
        start_date = today - timedelta(days=lookback_info["days"])
    else:
        start_date = None  # All time

    if start_date:
        recent_expenses_query = recent_expenses_query.filter(Expense.expense_date >= start_date)

    # Filter by category filters
    if category_filters and len(category_filters) > 0:
        recent_expenses_query = recent_expenses_query.filter(Expense.category_id.in_(category_filters))
    
    # Filter by vendor filters
    if vendor_filters and len(vendor_filters) > 0:
        recent_expenses_query = recent_expenses_query.filter(Expense.vendor_id.in_(vendor_filters))

    recent_expenses = recent_expenses_query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).offset(offset).limit(per_page).all()

    # Filter total expenses by lookback period
    total_expenses = recent_expenses_query.count()
    total_pages = (total_expenses + per_page - 1) // per_page
    
    # Get stats for visualizations with lookback, category, and vendor filters
    stats = get_expense_stats(db, user.id, lookback, category_filters if category_filters else None, vendor_filters if vendor_filters else None)
    
    # Get selected category names for display
    selected_category_names = []
    if category_filters:
        for cat_id in category_filters:
            cat = db.query(Category).filter(Category.id == cat_id).first()
            if cat:
                selected_category_names.append(cat.name)
    
    # Get selected vendor names for display
    selected_vendor_names = []
    if vendor_filters:
        for vendor_id in vendor_filters:
            vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
            if vendor:
                selected_vendor_names.append(vendor.name)
    
    profile_picture_b64, profile_picture_type = get_profile_picture_data(user)
    
    return templates.TemplateResponse("expenses.html", {
        "request": request,
        "title": "Expenses",
        "user": user,
        "categories": categories,
        "vendors": vendors,
        "recent_expenses": recent_expenses,
        "stats": stats,
        "subcategory_stats": stats.get("subcategory_stats", []),
        "subcategory_chart_data": stats.get("subcategory_chart_data", []),
        "vendor_stats": stats.get("vendor_stats", []),
        "today": date.today().isoformat(),
        "page": page,
        "total_pages": total_pages,
        "total_expenses": total_expenses,
        "show_all": show_all,
        "float": float,
        "lookback_periods": LOOKBACK_PERIODS,
        "current_lookback": lookback,
        "category_filters": category_filters,
        "categories_filter_str": categories_filter,
        "selected_category_names": selected_category_names,
        "vendor_filters": vendor_filters,
        "vendors_filter_str": vendors_filter,
        "selected_vendor_names": selected_vendor_names,
        "profile_picture_b64": profile_picture_b64,
        "profile_picture_type": profile_picture_type,
        "dark_mode": user.dark_mode
    })


@router.post("/expenses/add")
def add_expense(
    request: Request,
    db: Session = Depends(get_db),
    category_id: int = Form(...),
    subcategory_id: Optional[int] = Form(None),
    vendor_id: Optional[int] = Form(None),
    amount: float = Form(...),
    expense_date: str = Form(...),
    notes: Optional[str] = Form(None),
    is_recurring: Optional[str] = Form(None),
    frequency: Optional[str] = Form(None)
):
    """
    Add a new expense entry.
    
    Supports both one-time and recurring expenses. For recurring expenses,
    the frequency specifies how often the expense occurs.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Parse the date
    try:
        parsed_date = datetime.strptime(expense_date, "%Y-%m-%d").date()
    except ValueError:
        parsed_date = date.today()
    
    # Verify category belongs to user
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user.id
    ).first()
    
    if not category:
        return RedirectResponse("/expenses")
    
    # Verify vendor belongs to user (if provided)
    if vendor_id and vendor_id > 0:
        vendor = db.query(Vendor).filter(
            Vendor.id == vendor_id,
            Vendor.user_id == user.id
        ).first()
        if not vendor:
            vendor_id = None
    
    # Determine if recurring
    is_recurring_val = "yes" if is_recurring == "yes" else "no"
    frequency_val = frequency if is_recurring_val == "yes" and frequency else None
    
    # Create expense
    expense = Expense(
        user_id=user.id,
        category_id=category_id,
        subcategory_id=subcategory_id if subcategory_id and subcategory_id > 0 else None,
        vendor_id=vendor_id if vendor_id and vendor_id > 0 else None,
        amount=amount,
        expense_date=parsed_date,
        notes=notes if notes and notes.strip() else None,
        is_recurring=is_recurring_val,
        frequency=frequency_val
    )
    db.add(expense)
    db.commit()
    
    return RedirectResponse("/expenses", status_code=303)


@router.post("/expenses/category/add")
def add_category(
    request: Request,
    db: Session = Depends(get_db),
    category_name: str = Form(...)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Check if category already exists
    existing = db.query(Category).filter(
        Category.user_id == user.id,
        Category.name == category_name.strip()
    ).first()
    
    if existing:
        return JSONResponse({"id": existing.id, "name": existing.name})
    
    # Create new category
    category = Category(user_id=user.id, name=category_name.strip())
    db.add(category)
    db.commit()
    db.refresh(category)
    
    return JSONResponse({"id": category.id, "name": category.name})


@router.post("/expenses/subcategory/add")
def add_subcategory(
    request: Request,
    db: Session = Depends(get_db),
    category_id: int = Form(...),
    subcategory_name: str = Form(...)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Verify category belongs to user
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user.id
    ).first()
    
    if not category:
        return JSONResponse({"error": "Category not found"}, status_code=404)
    
    # Check if subcategory already exists
    existing = db.query(SubCategory).filter(
        SubCategory.category_id == category_id,
        SubCategory.name == subcategory_name.strip()
    ).first()
    
    if existing:
        return JSONResponse({"id": existing.id, "name": existing.name})
    
    # Create new subcategory
    subcategory = SubCategory(category_id=category_id, name=subcategory_name.strip())
    db.add(subcategory)
    db.commit()
    db.refresh(subcategory)
    
    return JSONResponse({"id": subcategory.id, "name": subcategory.name})


@router.get("/api/subcategories/{category_id}")
def get_subcategories(category_id: int, request: Request, db: Session = Depends(get_db)):
    """API endpoint to get subcategories for a category."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Verify category belongs to user
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user.id
    ).first()
    
    if not category:
        return JSONResponse({"subcategories": []})
    
    subcategories = [{"id": s.id, "name": s.name} for s in category.subcategories]
    return JSONResponse({"subcategories": subcategories})


@router.get("/api/expense/{expense_id}")
def get_expense(expense_id: int, request: Request, db: Session = Depends(get_db)):
    """Get a single expense for editing."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == user.id
    ).first()
    
    if not expense:
        return JSONResponse({"error": "Expense not found"}, status_code=404)
    
    return JSONResponse({
        "id": expense.id,
        "category_id": expense.category_id,
        "subcategory_id": expense.subcategory_id,
        "vendor_id": expense.vendor_id,
        "amount": expense.amount,
        "expense_date": expense.expense_date.isoformat(),
        "notes": expense.notes or ""
    })


@router.post("/expenses/update/{expense_id}")
def update_expense(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
    category_id: int = Form(...),
    subcategory_id: Optional[int] = Form(None),
    vendor_id: Optional[int] = Form(None),
    amount: float = Form(...),
    expense_date: str = Form(...),
    notes: Optional[str] = Form(None)
):
    """Update an existing expense."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == user.id
    ).first()
    
    if not expense:
        return RedirectResponse("/expenses")
    
    # Parse the date
    try:
        parsed_date = datetime.strptime(expense_date, "%Y-%m-%d").date()
    except ValueError:
        parsed_date = expense.expense_date
    
    # Verify category belongs to user
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user.id
    ).first()
    
    if not category:
        return RedirectResponse("/expenses")
    
    # Verify vendor belongs to user (if provided)
    if vendor_id and vendor_id > 0:
        vendor = db.query(Vendor).filter(
            Vendor.id == vendor_id,
            Vendor.user_id == user.id
        ).first()
        if not vendor:
            vendor_id = None
    
    # Update expense
    expense.category_id = category_id
    expense.subcategory_id = subcategory_id if subcategory_id and subcategory_id > 0 else None
    expense.vendor_id = vendor_id if vendor_id and vendor_id > 0 else None
    expense.amount = amount
    expense.expense_date = parsed_date
    expense.notes = notes if notes and notes.strip() else None
    
    db.commit()
    
    return RedirectResponse("/expenses", status_code=303)


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete an expense."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == user.id
    ).first()
    
    if expense:
        db.delete(expense)
        db.commit()
        return JSONResponse({"success": True})
    
    return JSONResponse({"error": "Expense not found"}, status_code=404)


@router.delete("/expenses/category/{category_id}")
def delete_category(category_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a category and all its subcategories. Expenses must be reassigned first."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user.id
    ).first()
    
    if not category:
        return JSONResponse({"error": "Category not found"}, status_code=404)
    
    # Check if there are expenses using this category
    expense_count = db.query(Expense).filter(Expense.category_id == category_id).count()
    if expense_count > 0:
        return JSONResponse({
            "error": f"Cannot delete category with {expense_count} expense(s). Delete or reassign expenses first.",
            "expense_count": expense_count
        }, status_code=400)
    
    # Delete the category (cascade will delete subcategories)
    db.delete(category)
    db.commit()
    return JSONResponse({"success": True})


@router.delete("/expenses/subcategory/{subcategory_id}")
def delete_subcategory(subcategory_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a subcategory. Expenses using it will have subcategory set to null."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    subcategory = db.query(SubCategory).filter(SubCategory.id == subcategory_id).first()
    
    if not subcategory:
        return JSONResponse({"error": "Subcategory not found"}, status_code=404)
    
    # Verify user owns the parent category
    category = db.query(Category).filter(
        Category.id == subcategory.category_id,
        Category.user_id == user.id
    ).first()
    
    if not category:
        return JSONResponse({"error": "Not authorized"}, status_code=403)
    
    # Update expenses to remove subcategory reference
    db.query(Expense).filter(Expense.subcategory_id == subcategory_id).update(
        {"subcategory_id": None}
    )
    
    # Delete the subcategory
    db.delete(subcategory)
    db.commit()
    return JSONResponse({"success": True})


# =============================================================================
# Vendor Management
# =============================================================================

@router.post("/expenses/vendor/add")
def add_vendor(
    request: Request,
    db: Session = Depends(get_db),
    vendor_name: str = Form(...)
):
    """Add a new vendor."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Check if vendor already exists
    existing = db.query(Vendor).filter(
        Vendor.user_id == user.id,
        Vendor.name == vendor_name.strip()
    ).first()
    
    if existing:
        return JSONResponse({"id": existing.id, "name": existing.name})
    
    # Create new vendor
    vendor = Vendor(user_id=user.id, name=vendor_name.strip())
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    
    return JSONResponse({"id": vendor.id, "name": vendor.name})


@router.get("/api/vendors")
def get_vendors(request: Request, db: Session = Depends(get_db)):
    """API endpoint to get all vendors for a user."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    vendors = db.query(Vendor).filter(Vendor.user_id == user.id).order_by(Vendor.name).all()
    
    result = []
    for vendor in vendors:
        expense_count = db.query(Expense).filter(Expense.vendor_id == vendor.id).count()
        total_spent = db.query(func.sum(Expense.amount)).filter(Expense.vendor_id == vendor.id).scalar() or 0
        result.append({
            "id": vendor.id,
            "name": vendor.name,
            "expense_count": expense_count,
            "total_spent": total_spent
        })
    
    return JSONResponse({"vendors": result})


@router.delete("/expenses/vendor/{vendor_id}")
def delete_vendor(vendor_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a vendor. Expenses using it will have vendor set to null."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id,
        Vendor.user_id == user.id
    ).first()
    
    if not vendor:
        return JSONResponse({"error": "Vendor not found"}, status_code=404)
    
    # Update expenses to remove vendor reference
    db.query(Expense).filter(Expense.vendor_id == vendor_id).update(
        {"vendor_id": None}
    )
    
    # Delete the vendor
    db.delete(vendor)
    db.commit()
    return JSONResponse({"success": True})


@router.post("/expenses/vendor/{vendor_id}/update")
def update_vendor(
    vendor_id: int,
    request: Request,
    db: Session = Depends(get_db),
    vendor_name: str = Form(...)
):
    """Update a vendor name."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id,
        Vendor.user_id == user.id
    ).first()
    
    if not vendor:
        return JSONResponse({"error": "Vendor not found"}, status_code=404)
    
    vendor.name = vendor_name.strip()
    db.commit()
    
    return JSONResponse({"success": True, "id": vendor.id, "name": vendor.name})


@router.get("/api/categories")
def get_categories(request: Request, db: Session = Depends(get_db)):
    """API endpoint to get all categories with subcategories for a user."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    categories = db.query(Category).filter(Category.user_id == user.id).order_by(Category.name).all()
    
    result = []
    for cat in categories:
        expense_count = db.query(Expense).filter(Expense.category_id == cat.id).count()
        subcats = []
        for sub in cat.subcategories:
            sub_expense_count = db.query(Expense).filter(Expense.subcategory_id == sub.id).count()
            subcats.append({
                "id": sub.id,
                "name": sub.name,
                "expense_count": sub_expense_count
            })
        result.append({
            "id": cat.id,
            "name": cat.name,
            "expense_count": expense_count,
            "subcategories": subcats
        })
    
    return JSONResponse({"categories": result})


@router.get("/api/stats")
def get_stats_api(
    request: Request,
    db: Session = Depends(get_db),
    lookback: str = Query("1m"),
    categories_filter: str = Query("")  # Comma-separated category IDs
):
    """API endpoint to get expense statistics with filters."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Parse category filters
    category_filters = []
    if categories_filter:
        try:
            category_filters = [int(c.strip()) for c in categories_filter.split(",") if c.strip()]
        except ValueError:
            category_filters = []
    
    stats = get_expense_stats(db, user.id, lookback, category_filters if category_filters else None)
    return JSONResponse(stats)


@router.get("/expenses/csv-template")
def download_csv_template(request: Request, db: Session = Depends(get_db)):
    """Download a CSV template for bulk expense upload."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Get user's categories and subcategories
    categories = db.query(Category).filter(Category.user_id == user.id).order_by(Category.name).all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        "date",           # YYYY-MM-DD format
        "amount",         # Numeric value
        "category",       # Category name (must match existing or will be created)
        "subcategory",    # Subcategory name (optional, must match existing or will be created)
        "notes"           # Optional notes
    ])
    
    # Example rows
    today = date.today().isoformat()
    writer.writerow([today, "25.99", "Groceries", "Food", "Weekly grocery shopping"])
    writer.writerow([today, "9.99", "Entertainment", "Streaming", "Netflix subscription"])
    writer.writerow([today, "50.00", "Transportation", "", "Gas fill-up"])
    
    # Add a comment section with instructions
    writer.writerow([])
    writer.writerow(["# INSTRUCTIONS:"])
    writer.writerow(["# - date: Use YYYY-MM-DD format (e.g., 2025-12-14)"])
    writer.writerow(["# - amount: Numeric value (e.g., 25.99)"])
    writer.writerow(["# - category: Required. If category doesn't exist, it will be created"])
    writer.writerow(["# - subcategory: Optional. If provided but doesn't exist, it will be created"])
    writer.writerow(["# - notes: Optional description"])
    writer.writerow([])
    writer.writerow(["# YOUR EXISTING CATEGORIES:"])
    
    for cat in categories:
        subcats = ", ".join([s.name for s in cat.subcategories]) if cat.subcategories else "(no subcategories)"
        writer.writerow([f"# {cat.name}: {subcats}"])
    
    # Seek to beginning of stream
    output.seek(0)
    
    # Return as downloadable file
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expense_upload_template.csv"}
    )


@router.get("/expenses/csv-export")
def export_expenses_csv(
    request: Request, 
    db: Session = Depends(get_db),
    lookback: str = Query("all")
):
    """Export all expenses as CSV with optional time filter."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Get lookback period
    lookback_info = LOOKBACK_PERIODS.get(lookback, {"days": None, "label": "All Time"})
    
    # Build query
    query = db.query(Expense).filter(Expense.user_id == user.id)
    
    if lookback_info["days"]:
        start_date = date.today() - timedelta(days=lookback_info["days"])
        query = query.filter(Expense.expense_date >= start_date)
    
    expenses = query.order_by(Expense.expense_date.desc()).all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        "date",
        "amount",
        "category",
        "subcategory",
        "notes",
        "is_recurring",
        "frequency"
    ])
    
    # Write all expenses
    for expense in expenses:
        writer.writerow([
            expense.expense_date.strftime("%Y-%m-%d"),
            f"{expense.amount:.2f}",
            expense.category.name if expense.category else "",
            expense.subcategory.name if expense.subcategory else "",
            expense.notes or "",
            expense.is_recurring or "",
            expense.frequency or ""
        ])
    
    output.seek(0)
    
    logger.info(f"Expenses CSV exported for user {user.username}: {len(expenses)} expenses")
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=expenses_export_{date.today().isoformat()}.csv"}
    )


@router.post("/expenses/bulk-upload")
async def bulk_upload_expenses(
    request: Request,
    db: Session = Depends(get_db),
    csv_file: UploadFile = File(...)
):
    """Bulk upload expenses from CSV file."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Check file type
    if not csv_file.filename.endswith('.csv'):
        return JSONResponse({"error": "Please upload a CSV file"}, status_code=400)
    
    # Read file content
    content = await csv_file.read()
    
    try:
        # Decode and parse CSV
        decoded = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        
        # Track results
        results = {
            "success": 0,
            "errors": [],
            "categories_created": [],
            "subcategories_created": []
        }
        
        # Cache for categories/subcategories
        category_cache = {}
        for cat in db.query(Category).filter(Category.user_id == user.id).all():
            category_cache[cat.name.lower()] = cat
        
        row_num = 1
        for row in reader:
            row_num += 1
            
            # Skip comment rows
            if row.get('date', '').startswith('#'):
                continue
            
            # Skip empty rows
            if not row.get('date') or not row.get('amount') or not row.get('category'):
                continue
            
            try:
                # Parse date
                try:
                    expense_date = datetime.strptime(row['date'].strip(), "%Y-%m-%d").date()
                except ValueError:
                    results["errors"].append(f"Row {row_num}: Invalid date format '{row['date']}' (use YYYY-MM-DD)")
                    continue
                
                # Parse amount
                try:
                    amount = float(row['amount'].strip().replace('$', '').replace(',', ''))
                    if amount <= 0:
                        raise ValueError("Amount must be positive")
                except ValueError as e:
                    results["errors"].append(f"Row {row_num}: Invalid amount '{row['amount']}'")
                    continue
                
                # Get or create category
                category_name = row['category'].strip()
                category_key = category_name.lower()
                
                if category_key in category_cache:
                    category = category_cache[category_key]
                else:
                    # Create new category
                    category = Category(user_id=user.id, name=category_name)
                    db.add(category)
                    db.flush()  # Get the ID
                    category_cache[category_key] = category
                    results["categories_created"].append(category_name)
                
                # Get or create subcategory (if provided)
                subcategory = None
                subcategory_name = row.get('subcategory', '').strip()
                
                if subcategory_name:
                    # Check if subcategory exists for this category
                    existing_sub = db.query(SubCategory).filter(
                        SubCategory.category_id == category.id,
                        SubCategory.name == subcategory_name
                    ).first()
                    
                    if existing_sub:
                        subcategory = existing_sub
                    else:
                        # Create new subcategory
                        subcategory = SubCategory(category_id=category.id, name=subcategory_name)
                        db.add(subcategory)
                        db.flush()
                        results["subcategories_created"].append(f"{category_name} > {subcategory_name}")
                
                # Create expense
                notes = row.get('notes', '').strip() or None
                
                expense = Expense(
                    user_id=user.id,
                    category_id=category.id,
                    subcategory_id=subcategory.id if subcategory else None,
                    amount=amount,
                    expense_date=expense_date,
                    notes=notes
                )
                db.add(expense)
                results["success"] += 1
                
            except Exception as e:
                results["errors"].append(f"Row {row_num}: {str(e)}")
        
        # Commit all changes
        db.commit()
        
        return JSONResponse({
            "success": True,
            "message": f"Imported {results['success']} expenses",
            "details": results
        })
        
    except Exception as e:
        return JSONResponse({"error": f"Failed to parse CSV: {str(e)}"}, status_code=400)

