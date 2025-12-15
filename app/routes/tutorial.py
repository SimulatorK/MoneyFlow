"""
Tutorial routes for MoneyFlow application.

This module handles the first-time user onboarding experience:
- Display tutorial page for new users
- Save income, expense, and budget data from tutorial steps
- Mark tutorial as complete

Routes:
    GET  /tutorial           - Display tutorial page
    POST /tutorial/save-income   - Save income data from step 1
    POST /tutorial/save-expense  - Save first expense from step 2
    POST /tutorial/save-budget   - Save first budget item from step 3
    POST /tutorial/complete      - Mark tutorial as completed
"""

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime

from app.db import get_db
from app.models.user import User
from app.models.income_taxes import IncomeTaxes
from app.models.expense import Category, Expense
from app.models.budget import FixedCost
from app.logging_config import get_logger

# Module logger
logger = get_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_current_user(request: Request, db: Session):
    """Get the logged-in user from cookies."""
    username = request.cookies.get("username")
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()


@router.get("/tutorial")
def tutorial_page(request: Request, db: Session = Depends(get_db)):
    """
    Display the onboarding tutorial for new users.
    
    Redirects to home if tutorial is already completed.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # If tutorial already completed, redirect to home
    if user.tutorial_completed:
        return RedirectResponse("/home")
    
    logger.info(f"Tutorial page accessed by user: {user.username}")
    
    return templates.TemplateResponse("tutorial.html", {
        "request": request,
        "user": user
    })


@router.post("/tutorial/save-income")
async def save_tutorial_income(
    request: Request,
    base_salary: float = Form(...),
    pay_frequency: str = Form(...),
    filing_status: str = Form("married_filing_jointly"),
    tax_year: int = Form(2025),
    db: Session = Depends(get_db)
):
    """
    Save income data from tutorial step 1.
    
    Creates or updates the IncomeTaxes record for the user.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        # Check if income record exists
        income = db.query(IncomeTaxes).filter(IncomeTaxes.user_id == user.id).first()
        
        if income:
            # Update existing
            income.base_salary = base_salary
            income.pay_frequency = pay_frequency
            income.filing_status = filing_status
            income.tax_year = tax_year
        else:
            # Create new
            income = IncomeTaxes(
                user_id=user.id,
                base_salary=base_salary,
                pay_frequency=pay_frequency,
                filing_status=filing_status,
                tax_year=tax_year
            )
            db.add(income)
        
        # Update tutorial progress
        user.tutorial_step = max(user.tutorial_step or 0, 1)
        
        db.commit()
        logger.info(f"Tutorial income saved for user {user.username}: ${base_salary}")
        
        return JSONResponse({"success": True})
        
    except Exception as e:
        logger.error(f"Error saving tutorial income: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/tutorial/save-expense")
async def save_tutorial_expense(
    request: Request,
    amount: float = Form(...),
    expense_date: str = Form(...),
    category: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    Save first expense from tutorial step 2.
    
    Creates category if it doesn't exist, then creates the expense.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        # Get or create category
        cat = db.query(Category).filter(
            Category.user_id == user.id,
            Category.name == category
        ).first()
        
        if not cat:
            cat = Category(user_id=user.id, name=category)
            db.add(cat)
            db.flush()
            logger.info(f"Created category '{category}' for user {user.username}")
        
        # Parse date
        try:
            parsed_date = datetime.strptime(expense_date, "%Y-%m-%d").date()
        except ValueError:
            parsed_date = date.today()
        
        # Create expense
        expense = Expense(
            user_id=user.id,
            category_id=cat.id,
            amount=amount,
            expense_date=parsed_date,
            notes=notes if notes else None
        )
        db.add(expense)
        
        # Update tutorial progress
        user.tutorial_step = max(user.tutorial_step or 0, 2)
        
        db.commit()
        logger.info(f"Tutorial expense saved for user {user.username}: ${amount} in {category}")
        
        return JSONResponse({"success": True})
        
    except Exception as e:
        logger.error(f"Error saving tutorial expense: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/tutorial/save-budget")
async def save_tutorial_budget(
    request: Request,
    name: str = Form(...),
    amount: float = Form(...),
    category_type: str = Form("need"),
    frequency: str = Form("monthly"),
    db: Session = Depends(get_db)
):
    """
    Save first budget item from tutorial step 3.
    
    Creates a FixedCost entry for the user.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        # Create fixed cost
        fixed_cost = FixedCost(
            user_id=user.id,
            name=name,
            amount=amount,
            category_type=category_type,
            frequency=frequency
        )
        db.add(fixed_cost)
        
        # Update tutorial progress
        user.tutorial_step = max(user.tutorial_step or 0, 3)
        
        db.commit()
        logger.info(f"Tutorial budget item saved for user {user.username}: {name} ${amount}")
        
        return JSONResponse({"success": True})
        
    except Exception as e:
        logger.error(f"Error saving tutorial budget: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/tutorial/complete")
async def complete_tutorial(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Mark the tutorial as completed for the user.
    
    Sets tutorial_completed to True and tutorial_step to 4.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        user.tutorial_completed = True
        user.tutorial_step = 4
        db.commit()
        
        logger.info(f"Tutorial completed for user {user.username}")
        
        return JSONResponse({"success": True})
        
    except Exception as e:
        logger.error(f"Error completing tutorial: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/tutorial/skip")
async def skip_tutorial(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Skip the tutorial (not exposed in UI but available as fallback).
    
    Marks tutorial as completed without saving any data.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        user.tutorial_completed = True
        user.tutorial_step = 0  # Indicates skipped
        db.commit()
        
        logger.info(f"Tutorial skipped by user {user.username}")
        
        return JSONResponse({"success": True})
        
    except Exception as e:
        logger.error(f"Error skipping tutorial: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)

