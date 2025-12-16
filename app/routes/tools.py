"""
Tools routes for MoneyFlow application.

This module provides financial calculators and planning tools including:
- Mortgage/home loan calculator with scenario comparison
- Net Worth Manager for tracking assets and liabilities
- Save/load mortgage scenarios to database

Routes:
    GET /tools - Main tools page with mortgage calculator
    POST /tools/mortgage/save - Save a mortgage scenario
    GET /tools/mortgage/load/{id} - Load a saved mortgage scenario
    DELETE /tools/mortgage/delete/{id} - Delete a saved mortgage scenario
    
    Net Worth Manager:
    POST /tools/networth/account/add - Add a new account
    POST /tools/networth/account/{id}/update - Update an account
    DELETE /tools/networth/account/{id}/delete - Delete an account
    POST /tools/networth/balance/add - Add a balance entry
    DELETE /tools/networth/balance/{id}/delete - Delete a balance entry
    POST /tools/networth/contribution/update - Update contribution settings
    GET /tools/networth/data - Get all net worth data as JSON
"""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timedelta
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json

from app.db import get_db
from app.models.user import User
from app.models.mortgage import MortgageScenario
from app.models.networth import (
    Account, AccountBalance, AccountContribution, MonteCarloScenario,
    ACCOUNT_TYPES, FREQUENCY_CHOICES, HISTORICAL_RETURNS, TAX_TREATMENT
)
from app.logging_config import get_logger
import base64
import random
import numpy as np
import csv
import io
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse

# Module logger for tools operations
logger = get_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class MortgageSaveRequest(BaseModel):
    """Request model for saving a mortgage scenario."""
    name: str
    compareMode: bool
    scenarios: Dict[str, Any]


class AccountRequest(BaseModel):
    """Request model for creating/updating an account."""
    name: str
    account_type: str
    is_asset: bool
    institution: Optional[str] = None
    notes: Optional[str] = None


class BalanceRequest(BaseModel):
    """Request model for adding a balance entry."""
    account_id: int
    balance_date: str
    balance: float
    notes: Optional[str] = None


class ContributionRequest(BaseModel):
    """Request model for updating contribution settings."""
    account_id: int
    amount: float = 0
    frequency: str = "monthly"
    employer_match: float = 0
    employer_match_type: str = "percent"
    employer_match_limit: float = 0
    notes: Optional[str] = None


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


def calculate_performance_metrics(balances: list, current_balance: float, period: str = "all") -> dict:
    """
    Calculate performance metrics for an account or overall net worth.
    
    Args:
        balances: List of balance entries sorted by date
        current_balance: Current balance value
        period: Time period - "1m", "3m", "6m", "1y", "ytd", "2y", "5y", or "all"
        
    Returns:
        Dictionary with cumulative and annualized % changes
    """
    if not balances or len(balances) < 1:
        return {
            "cumulative_change": 0,
            "cumulative_pct": 0,
            "annualized_pct": 0,
            "first_date": None,
            "first_balance": current_balance,
            "days_tracked": 0,
            "period": period,
            "period_label": get_period_label(period)
        }
    
    sorted_balances = sorted(balances, key=lambda b: b.balance_date if hasattr(b, 'balance_date') else b['date'])
    
    # Calculate start date based on period
    today = date.today()
    period_start_date = None  # The target start date for the period
    
    if period == "1m":
        period_start_date = today - timedelta(days=30)
    elif period == "3m":
        period_start_date = today - timedelta(days=90)
    elif period == "6m":
        period_start_date = today - timedelta(days=180)
    elif period == "1y":
        period_start_date = today - timedelta(days=365)
    elif period == "ytd":
        period_start_date = date(today.year, 1, 1)
    elif period == "2y":
        period_start_date = today - timedelta(days=730)
    elif period == "5y":
        period_start_date = today - timedelta(days=1825)
    # else: "all" - period_start_date stays None
    
    # Find the balance to use as the starting point
    if period_start_date:
        # Find the balance closest to (but not after) the period start date
        # OR the first balance after if none before
        balances_before = []
        balances_after = []
        
        for b in sorted_balances:
            b_date = b.balance_date if hasattr(b, 'balance_date') else datetime.strptime(b['date'], '%Y-%m-%d').date()
            if b_date <= period_start_date:
                balances_before.append((b, b_date))
            else:
                balances_after.append((b, b_date))
        
        if balances_before:
            # Use the most recent balance before/on the period start
            first, first_date = balances_before[-1]
        elif balances_after:
            # No balance before period start, use the first available after
            first, first_date = balances_after[0]
        else:
            first = sorted_balances[0]
            first_date = first.balance_date if hasattr(first, 'balance_date') else datetime.strptime(first['date'], '%Y-%m-%d').date()
    else:
        # "all" time - use very first balance
        first = sorted_balances[0]
        first_date = first.balance_date if hasattr(first, 'balance_date') else datetime.strptime(first['date'], '%Y-%m-%d').date()
    
    first_balance = first.balance if hasattr(first, 'balance') else first['balance']
    
    # Calculate the actual days in the measurement period
    days_tracked = (today - first_date).days
    
    if first_balance == 0:
        return {
            "cumulative_change": current_balance,
            "cumulative_pct": 0,
            "annualized_pct": 0,
            "first_date": first_date.isoformat() if first_date else None,
            "first_balance": first_balance,
            "days_tracked": days_tracked,
            "period": period,
            "period_label": get_period_label(period)
        }
    
    cumulative_change = current_balance - first_balance
    cumulative_pct = (cumulative_change / abs(first_balance)) * 100
    
    # Calculate annualized return
    if days_tracked > 0 and first_balance > 0:
        years = days_tracked / 365.25
        if years > 0 and current_balance > 0:
            # CAGR formula: (ending/beginning)^(1/years) - 1
            annualized_pct = ((current_balance / first_balance) ** (1 / years) - 1) * 100
        else:
            annualized_pct = 0
    else:
        annualized_pct = 0
    
    return {
        "cumulative_change": cumulative_change,
        "cumulative_pct": cumulative_pct,
        "annualized_pct": annualized_pct,
        "first_date": first_date.isoformat() if first_date else None,
        "first_balance": first_balance,
        "days_tracked": days_tracked,
        "period": period,
        "period_label": get_period_label(period)
    }


def get_period_label(period: str) -> str:
    """Get human-readable label for a period."""
    labels = {
        "1m": "1 Month",
        "3m": "3 Months",
        "6m": "6 Months",
        "1y": "1 Year",
        "ytd": "Year to Date",
        "2y": "2 Years",
        "5y": "5 Years",
        "all": "All Time"
    }
    return labels.get(period, "All Time")


def calculate_net_worth_summary(accounts: List[Account]) -> dict:
    """
    Calculate net worth summary from accounts including performance metrics.
    
    Returns:
        Dictionary with total assets, liabilities, net worth, account details, and performance
    """
    total_assets = 0
    total_liabilities = 0
    account_details = []
    all_asset_balances = []
    all_liability_balances = []
    
    for account in accounts:
        # Get the most recent balance
        latest_balance = None
        if account.balances:
            latest_balance = max(account.balances, key=lambda b: b.balance_date)
        
        current_balance = latest_balance.balance if latest_balance else 0
        
        if account.is_asset:
            total_assets += current_balance
        else:
            total_liabilities += current_balance
        
        # Calculate performance for this account
        performance = calculate_performance_metrics(account.balances, current_balance)
        
        account_details.append({
            "id": account.id,
            "name": account.name,
            "account_type": account.account_type,
            "is_asset": account.is_asset,
            "institution": account.institution,
            "current_balance": current_balance,
            "latest_date": latest_balance.balance_date.isoformat() if latest_balance else None,
            "performance": performance,
            "contribution": {
                "amount": account.contribution.amount if account.contribution.amount is not None else 0,
                "frequency": account.contribution.frequency if account.contribution.frequency else "monthly",
                "employer_match": account.contribution.employer_match if account.contribution.employer_match is not None else 0,
                "employer_match_type": account.contribution.employer_match_type if account.contribution.employer_match_type else "percent",
                "expected_return": account.contribution.expected_return if account.contribution.expected_return is not None else 7.0,
                "interest_rate": account.contribution.interest_rate if account.contribution.interest_rate is not None else 0,
                "stocks_pct": account.contribution.stocks_pct if account.contribution.stocks_pct is not None else 80.0,
                "bonds_pct": account.contribution.bonds_pct if account.contribution.bonds_pct is not None else 15.0,
                "cash_pct": account.contribution.cash_pct if account.contribution.cash_pct is not None else 5.0,
            } if account.contribution else None
        })
        
        # Collect balances for overall performance calculation
        for bal in account.balances:
            entry = {"date": bal.balance_date.isoformat(), "balance": bal.balance if account.is_asset else -bal.balance}
            if account.is_asset:
                all_asset_balances.append(entry)
            else:
                all_liability_balances.append(entry)
    
    net_worth = total_assets - total_liabilities
    
    # Calculate overall net worth performance (combining assets - liabilities over time)
    # Group by date and sum
    from collections import defaultdict
    net_worth_by_date = defaultdict(float)
    for entry in all_asset_balances:
        net_worth_by_date[entry['date']] += entry['balance']
    for entry in all_liability_balances:
        net_worth_by_date[entry['date']] += entry['balance']  # Already negated
    
    # Convert to list format for calculate_performance_metrics
    net_worth_history = [{"date": d, "balance": b} for d, b in sorted(net_worth_by_date.items())]
    overall_performance = calculate_performance_metrics(net_worth_history, net_worth) if net_worth_history else {
        "cumulative_change": 0, "cumulative_pct": 0, "annualized_pct": 0,
        "first_date": None, "first_balance": net_worth, "days_tracked": 0
    }
    
    # Calculate tax analysis breakdown
    tax_analysis = calculate_tax_analysis(accounts)
    
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "accounts": account_details,
        "performance": overall_performance,
        "tax_analysis": tax_analysis
    }


def calculate_tax_analysis(accounts: List[Account]) -> dict:
    """
    Analyze portfolio tax treatment to help users understand tax implications.
    
    Categories:
    - tax_free: Roth accounts, HSA - qualified withdrawals are tax-free
    - tax_deferred: Traditional 401k, IRA - withdrawals taxed as ordinary income
    - taxable: Brokerage, savings - subject to capital gains
    - partially_taxable: After-tax 401k - basis tax-free, gains taxed
    
    Returns:
        Dictionary with breakdown of balances by tax treatment
    """
    tax_free = 0.0         # Roth accounts, HSA
    tax_deferred = 0.0     # Traditional 401k, IRA
    taxable = 0.0          # Brokerage, savings, etc.
    partially_taxable = 0.0  # After-tax 401k
    total_assets = 0.0
    
    accounts_by_tax_type = {
        "tax_free": [],
        "tax_deferred": [],
        "taxable": [],
        "partially_taxable": []
    }
    
    for account in accounts:
        if not account.is_asset:
            continue  # Skip liabilities
            
        current_balance = 0
        if account.balances:
            latest = max(account.balances, key=lambda b: b.balance_date)
            current_balance = latest.balance
        
        total_assets += current_balance
        
        # Determine tax treatment
        treatment = TAX_TREATMENT.get(account.account_type, "taxable")
        
        account_info = {
            "name": account.name,
            "balance": current_balance,
            "type": account.account_type
        }
        
        if treatment == "tax_free":
            tax_free += current_balance
            accounts_by_tax_type["tax_free"].append(account_info)
        elif treatment == "tax_deferred":
            tax_deferred += current_balance
            accounts_by_tax_type["tax_deferred"].append(account_info)
        elif treatment == "partially_taxable":
            partially_taxable += current_balance
            accounts_by_tax_type["partially_taxable"].append(account_info)
        else:  # taxable
            taxable += current_balance
            accounts_by_tax_type["taxable"].append(account_info)
    
    # Calculate percentages
    tax_free_pct = (tax_free / total_assets * 100) if total_assets > 0 else 0
    tax_deferred_pct = (tax_deferred / total_assets * 100) if total_assets > 0 else 0
    taxable_pct = (taxable / total_assets * 100) if total_assets > 0 else 0
    partially_taxable_pct = (partially_taxable / total_assets * 100) if total_assets > 0 else 0
    
    return {
        "total_assets": total_assets,
        "tax_free": {
            "amount": tax_free,
            "percentage": tax_free_pct,
            "accounts": accounts_by_tax_type["tax_free"],
            "description": "Roth accounts, HSA - Qualified withdrawals are tax-free"
        },
        "tax_deferred": {
            "amount": tax_deferred,
            "percentage": tax_deferred_pct,
            "accounts": accounts_by_tax_type["tax_deferred"],
            "description": "Traditional 401(k), IRA - Withdrawals taxed as ordinary income"
        },
        "taxable": {
            "amount": taxable,
            "percentage": taxable_pct,
            "accounts": accounts_by_tax_type["taxable"],
            "description": "Brokerage, Savings - Subject to capital gains tax"
        },
        "partially_taxable": {
            "amount": partially_taxable,
            "percentage": partially_taxable_pct,
            "accounts": accounts_by_tax_type["partially_taxable"],
            "description": "After-tax 401(k) - Basis tax-free, gains taxed"
        }
    }


@router.get("/tools")
def tools_page(request: Request, db: Session = Depends(get_db)):
    """
    Main tools page with financial calculators.
    
    Displays mortgage calculator, net worth manager, and loads saved data for the user.
    """
    user = get_current_user(request, db)
    if not user:
        logger.debug("Unauthenticated user redirected to login from tools page")
        return RedirectResponse("/login")
    
    logger.info(f"Tools page accessed by user: {user.username}")
    
    profile_picture_b64, profile_picture_type = get_profile_picture_data(user)
    
    # Current date for forms
    current_date = date.today().strftime("%Y-%m-%d")
    
    # Load saved mortgage scenarios for this user
    saved_scenarios = db.query(MortgageScenario).filter(
        MortgageScenario.user_id == user.id
    ).order_by(MortgageScenario.created_at.desc()).all()
    
    # Load net worth accounts for this user
    networth_accounts = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_active == True
    ).order_by(Account.is_asset.desc(), Account.name).all()
    
    networth_summary = calculate_net_worth_summary(networth_accounts)
    
    # Get balance history for chart (last 12 months)
    balance_history = []
    for account in networth_accounts:
        for balance in account.balances:
            balance_history.append({
                "account_id": account.id,
                "account_name": account.name,
                "is_asset": account.is_asset,
                "date": balance.balance_date.isoformat(),
                "balance": balance.balance
            })
    
    logger.debug(f"Loaded {len(saved_scenarios)} mortgage scenarios, {len(networth_accounts)} net worth accounts")
    
    return templates.TemplateResponse("tools.html", {
        "request": request,
        "title": "Tools",
        "user": user,
        "dark_mode": user.dark_mode,
        "profile_picture_b64": profile_picture_b64,
        "profile_picture_type": profile_picture_type,
        "current_date": current_date,
        "saved_scenarios": saved_scenarios,
        "networth_accounts": networth_accounts,
        "networth_summary": networth_summary,
        "balance_history": balance_history,
        "account_types": ACCOUNT_TYPES,
        "frequency_choices": FREQUENCY_CHOICES
    })


@router.post("/tools/mortgage/save")
async def save_mortgage_scenario(
    request: Request,
    data: MortgageSaveRequest,
    db: Session = Depends(get_db)
):
    """
    Save a mortgage scenario to the database.
    
    Args:
        data: MortgageSaveRequest containing scenario name and data
        
    Returns:
        JSON response with the saved scenario ID
    """
    user = get_current_user(request, db)
    if not user:
        logger.warning("Unauthenticated attempt to save mortgage scenario")
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Check scenario limit (max 5 per user)
    existing_count = db.query(MortgageScenario).filter(
        MortgageScenario.user_id == user.id
    ).count()
    
    if existing_count >= MAX_SCENARIOS_PER_TYPE:
        logger.warning(f"User {user.username} hit mortgage scenario limit ({MAX_SCENARIOS_PER_TYPE})")
        return JSONResponse({
            "error": f"Maximum of {MAX_SCENARIOS_PER_TYPE} saved scenarios allowed. Please delete an existing scenario first."
        }, status_code=400)
    
    try:
        scenario = MortgageScenario(
            user_id=user.id,
            name=data.name,
            compare_mode=data.compareMode,
            scenario_data=json.dumps(data.scenarios)
        )
        db.add(scenario)
        db.commit()
        db.refresh(scenario)
        
        logger.info(f"Mortgage scenario saved: {data.name} (ID: {scenario.id}) for user {user.username}")
        
        return JSONResponse({
            "success": True,
            "id": scenario.id,
            "name": scenario.name
        })
    except Exception as e:
        logger.error(f"Error saving mortgage scenario: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/tools/mortgage/load/{scenario_id}")
async def load_mortgage_scenario(
    request: Request,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Load a saved mortgage scenario from the database.
    
    Args:
        scenario_id: The ID of the scenario to load
        
    Returns:
        JSON response with the scenario data
    """
    user = get_current_user(request, db)
    if not user:
        logger.warning("Unauthenticated attempt to load mortgage scenario")
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    scenario = db.query(MortgageScenario).filter(
        MortgageScenario.id == scenario_id,
        MortgageScenario.user_id == user.id
    ).first()
    
    if not scenario:
        logger.warning(f"Mortgage scenario {scenario_id} not found for user {user.username}")
        return JSONResponse({"error": "Scenario not found"}, status_code=404)
    
    logger.info(f"Mortgage scenario loaded: {scenario.name} (ID: {scenario_id}) for user {user.username}")
    
    return JSONResponse({
        "id": scenario.id,
        "name": scenario.name,
        "compareMode": scenario.compare_mode,
        "scenarios": json.loads(scenario.scenario_data)
    })


@router.delete("/tools/mortgage/delete/{scenario_id}")
async def delete_mortgage_scenario(
    request: Request,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a saved mortgage scenario from the database.
    
    Args:
        scenario_id: The ID of the scenario to delete
        
    Returns:
        JSON response confirming deletion
    """
    user = get_current_user(request, db)
    if not user:
        logger.warning("Unauthenticated attempt to delete mortgage scenario")
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    scenario = db.query(MortgageScenario).filter(
        MortgageScenario.id == scenario_id,
        MortgageScenario.user_id == user.id
    ).first()
    
    if not scenario:
        logger.warning(f"Mortgage scenario {scenario_id} not found for user {user.username}")
        return JSONResponse({"error": "Scenario not found"}, status_code=404)
    
    db.delete(scenario)
    db.commit()
    
    logger.info(f"Mortgage scenario deleted: {scenario.name} (ID: {scenario_id}) for user {user.username}")
    
    return JSONResponse({"success": True})


# =============================================================================
# Net Worth Manager Routes
# =============================================================================

# Limits
MAX_SCENARIOS_PER_TYPE = 5
MAX_ACCOUNTS_PER_TYPE = 15


@router.post("/tools/networth/account/add")
async def add_networth_account(
    request: Request,
    name: str = Form(...),
    account_type: str = Form(...),
    is_asset: str = Form(...),
    institution: str = Form(None),
    notes: str = Form(None),
    initial_balance: float = Form(0),
    db: Session = Depends(get_db)
):
    """Add a new net worth account."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    is_asset_bool = (is_asset == "true")
    
    # Check account limits (15 per type)
    existing_count = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_asset == is_asset_bool,
        Account.is_active == True
    ).count()
    
    if existing_count >= MAX_ACCOUNTS_PER_TYPE:
        account_type_name = "assets" if is_asset_bool else "liabilities"
        logger.warning(f"User {user.username} hit {account_type_name} account limit ({MAX_ACCOUNTS_PER_TYPE})")
        # Could add flash message here, for now just redirect
        return RedirectResponse(f"/tools?tab=networth&error=limit_reached_{account_type_name}", status_code=303)
    
    try:
        account = Account(
            user_id=user.id,
            name=name,
            account_type=account_type,
            is_asset=is_asset_bool,
            institution=institution or None,
            notes=notes or None
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        
        # Add initial balance if provided
        if initial_balance != 0:
            balance = AccountBalance(
                account_id=account.id,
                balance_date=date.today(),
                balance=initial_balance
            )
            db.add(balance)
            db.commit()
        
        logger.info(f"Net worth account added: {name} (ID: {account.id}) for user {user.username}")
        
    except Exception as e:
        logger.error(f"Error adding net worth account: {e}")
        db.rollback()
    
    return RedirectResponse("/tools?tab=networth", status_code=303)


@router.post("/tools/networth/account/{account_id}/update")
async def update_networth_account(
    request: Request,
    account_id: int,
    name: str = Form(...),
    account_type: str = Form(...),
    institution: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Update an existing net worth account."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user.id
    ).first()
    
    if not account:
        return RedirectResponse("/tools?tab=networth", status_code=303)
    
    try:
        account.name = name
        account.account_type = account_type
        account.institution = institution or None
        account.notes = notes or None
        db.commit()
        
        logger.info(f"Net worth account updated: {name} (ID: {account_id}) for user {user.username}")
        
    except Exception as e:
        logger.error(f"Error updating net worth account: {e}")
        db.rollback()
    
    return RedirectResponse("/tools?tab=networth", status_code=303)


@router.post("/tools/networth/account/{account_id}/delete")
async def delete_networth_account(
    request: Request,
    account_id: int,
    db: Session = Depends(get_db)
):
    """Delete a net worth account (soft delete by setting is_active=False)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user.id
    ).first()
    
    if account:
        try:
            # Hard delete - also deletes balances and contributions via cascade
            db.delete(account)
            db.commit()
            logger.info(f"Net worth account deleted: {account.name} (ID: {account_id}) for user {user.username}")
        except Exception as e:
            logger.error(f"Error deleting net worth account: {e}")
            db.rollback()
    
    return RedirectResponse("/tools?tab=networth", status_code=303)


@router.post("/tools/networth/balance/add")
async def add_balance_entry(
    request: Request,
    account_id: int = Form(...),
    balance_date: str = Form(...),
    balance: float = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Add a balance entry for an account."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    # Verify account belongs to user
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user.id
    ).first()
    
    if not account:
        return RedirectResponse("/tools?tab=networth", status_code=303)
    
    try:
        balance_entry = AccountBalance(
            account_id=account_id,
            balance_date=datetime.strptime(balance_date, "%Y-%m-%d").date(),
            balance=balance,
            notes=notes or None
        )
        db.add(balance_entry)
        db.commit()
        
        logger.info(f"Balance entry added for account {account.name}: ${balance} on {balance_date}")
        
    except Exception as e:
        logger.error(f"Error adding balance entry: {e}")
        db.rollback()
    
    return RedirectResponse("/tools?tab=networth", status_code=303)


@router.post("/tools/networth/balance/{balance_id}/delete")
async def delete_balance_entry(
    request: Request,
    balance_id: int,
    db: Session = Depends(get_db)
):
    """Delete a balance entry."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    # Verify balance belongs to user's account
    balance = db.query(AccountBalance).join(Account).filter(
        AccountBalance.id == balance_id,
        Account.user_id == user.id
    ).first()
    
    if balance:
        try:
            db.delete(balance)
            db.commit()
            logger.info(f"Balance entry deleted (ID: {balance_id})")
        except Exception as e:
            logger.error(f"Error deleting balance entry: {e}")
            db.rollback()
    
    return RedirectResponse("/tools?tab=networth", status_code=303)


class ContributionUpdateRequest(BaseModel):
    """Request model for updating contribution settings via JSON."""
    account_id: int
    amount: float = 0
    frequency: str = "monthly"
    employer_match: float = 0
    employer_match_type: str = "percent"
    employer_match_limit: float = 0
    expected_return: float = 7.0
    interest_rate: float = 0
    stocks_pct: float = 80.0
    bonds_pct: float = 15.0
    cash_pct: float = 5.0
    notes: Optional[str] = None


@router.post("/tools/networth/contribution/update")
async def update_contribution(
    request: Request,
    account_id: int = Form(...),
    amount: float = Form(0),
    frequency: str = Form("monthly"),
    employer_match: float = Form(0),
    employer_match_type: str = Form("percent"),
    employer_match_limit: float = Form(0),
    expected_return: float = Form(7.0),
    interest_rate: float = Form(0),
    stocks_pct: float = Form(80.0),
    bonds_pct: float = Form(15.0),
    cash_pct: float = Form(5.0),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Update contribution settings for an account (form submission)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    # Verify account belongs to user
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user.id
    ).first()
    
    if not account:
        return RedirectResponse("/tools?tab=networth", status_code=303)
    
    # Validate portfolio allocation sums to 100
    total_allocation = stocks_pct + bonds_pct + cash_pct
    if abs(total_allocation - 100.0) > 0.01:
        # Normalize to 100%
        if total_allocation > 0:
            stocks_pct = (stocks_pct / total_allocation) * 100
            bonds_pct = (bonds_pct / total_allocation) * 100
            cash_pct = (cash_pct / total_allocation) * 100
    
    try:
        # Get or create contribution
        contribution = db.query(AccountContribution).filter(
            AccountContribution.account_id == account_id
        ).first()
        
        if contribution:
            contribution.amount = amount
            contribution.frequency = frequency
            contribution.employer_match = employer_match
            contribution.employer_match_type = employer_match_type
            contribution.employer_match_limit = employer_match_limit
            contribution.expected_return = expected_return
            contribution.interest_rate = interest_rate
            contribution.stocks_pct = stocks_pct
            contribution.bonds_pct = bonds_pct
            contribution.cash_pct = cash_pct
            contribution.notes = notes or None
        else:
            contribution = AccountContribution(
                account_id=account_id,
                amount=amount,
                frequency=frequency,
                employer_match=employer_match,
                employer_match_type=employer_match_type,
                employer_match_limit=employer_match_limit,
                expected_return=expected_return,
                interest_rate=interest_rate,
                stocks_pct=stocks_pct,
                bonds_pct=bonds_pct,
                cash_pct=cash_pct,
                notes=notes or None
            )
            db.add(contribution)
        
        db.commit()
        logger.info(f"Contribution updated for account {account.name}: ${amount} {frequency} @ {expected_return}% (Stocks: {stocks_pct}%, Bonds: {bonds_pct}%, Cash: {cash_pct}%)")
        
    except Exception as e:
        logger.error(f"Error updating contribution: {e}")
        db.rollback()
    
    return RedirectResponse("/tools?tab=projections", status_code=303)


@router.post("/tools/networth/contribution/update-json")
async def update_contribution_json(
    request: Request,
    body: ContributionUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update contribution settings for an account (JSON API)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Verify account belongs to user
    account = db.query(Account).filter(
        Account.id == body.account_id,
        Account.user_id == user.id
    ).first()
    
    if not account:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    
    # Validate portfolio allocation sums to 100
    stocks_pct = body.stocks_pct
    bonds_pct = body.bonds_pct
    cash_pct = body.cash_pct
    total_allocation = stocks_pct + bonds_pct + cash_pct
    if abs(total_allocation - 100.0) > 0.01:
        if total_allocation > 0:
            stocks_pct = (stocks_pct / total_allocation) * 100
            bonds_pct = (bonds_pct / total_allocation) * 100
            cash_pct = (cash_pct / total_allocation) * 100
    
    try:
        contribution = db.query(AccountContribution).filter(
            AccountContribution.account_id == body.account_id
        ).first()
        
        if contribution:
            contribution.amount = body.amount
            contribution.frequency = body.frequency
            contribution.employer_match = body.employer_match
            contribution.employer_match_type = body.employer_match_type
            contribution.employer_match_limit = body.employer_match_limit
            contribution.expected_return = body.expected_return
            contribution.interest_rate = body.interest_rate
            contribution.stocks_pct = stocks_pct
            contribution.bonds_pct = bonds_pct
            contribution.cash_pct = cash_pct
            contribution.notes = body.notes
        else:
            contribution = AccountContribution(
                account_id=body.account_id,
                amount=body.amount,
                frequency=body.frequency,
                employer_match=body.employer_match,
                employer_match_type=body.employer_match_type,
                employer_match_limit=body.employer_match_limit,
                expected_return=body.expected_return,
                interest_rate=body.interest_rate,
                stocks_pct=stocks_pct,
                bonds_pct=bonds_pct,
                cash_pct=cash_pct,
                notes=body.notes
            )
            db.add(contribution)
        
        db.commit()
        logger.info(f"Contribution updated (JSON) for account {account.name}: ${body.amount} {body.frequency}")
        
        return JSONResponse({
            "success": True,
            "account_id": body.account_id,
            "amount": body.amount,
            "frequency": body.frequency,
            "expected_return": body.expected_return,
            "stocks_pct": stocks_pct,
            "bonds_pct": bonds_pct,
            "cash_pct": cash_pct
        })
        
    except Exception as e:
        logger.error(f"Error updating contribution: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/tools/networth/data")
async def get_networth_data(request: Request, db: Session = Depends(get_db)):
    """Get all net worth data as JSON for charts."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    accounts = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_active == True
    ).all()
    
    summary = calculate_net_worth_summary(accounts)
    
    # Get all balance history
    balance_history = []
    for account in accounts:
        for balance in sorted(account.balances, key=lambda b: b.balance_date):
            balance_history.append({
                "account_id": account.id,
                "account_name": account.name,
                "is_asset": account.is_asset,
                "date": balance.balance_date.isoformat(),
                "balance": balance.balance
            })
    
    return JSONResponse({
        "summary": summary,
        "balance_history": balance_history
    })


@router.get("/tools/networth/performance")
async def get_networth_performance(
    request: Request,
    period: str = "all",
    db: Session = Depends(get_db)
):
    """
    Get net worth performance metrics for a specific time period.
    
    Args:
        period: Time period - "1m", "3m", "6m", "1y", "ytd", "2y", "5y", or "all"
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Get all accounts with balances
    accounts = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_active == True
    ).all()
    
    if not accounts:
        return JSONResponse({
            "performance": {
                "cumulative_change": 0,
                "cumulative_pct": 0,
                "annualized_pct": 0,
                "first_date": None,
                "first_balance": 0,
                "days_tracked": 0,
                "period": period,
                "period_label": get_period_label(period)
            },
            "account_performance": []
        })
    
    # Calculate current net worth
    net_worth = 0
    for account in accounts:
        current_balance = 0
        if account.balances:
            latest = max(account.balances, key=lambda b: b.balance_date)
            current_balance = latest.balance
        if account.is_asset:
            net_worth += current_balance
        else:
            net_worth -= current_balance
    
    # Build combined net worth history across all accounts
    all_dates = set()
    for account in accounts:
        for balance in account.balances:
            all_dates.add(balance.balance_date)
    
    if not all_dates:
        return JSONResponse({
            "performance": {
                "cumulative_change": 0,
                "cumulative_pct": 0,
                "annualized_pct": 0,
                "first_date": None,
                "first_balance": net_worth,
                "days_tracked": 0,
                "period": period,
                "period_label": get_period_label(period)
            },
            "account_performance": []
        })
    
    # Sort dates
    sorted_dates = sorted(all_dates)
    
    # Build net worth for each date
    net_worth_history = []
    for dt in sorted_dates:
        date_nw = 0
        for account in accounts:
            # Find balance on or before this date
            account_balances = [b for b in account.balances if b.balance_date <= dt]
            if account_balances:
                latest = max(account_balances, key=lambda b: b.balance_date)
                if account.is_asset:
                    date_nw += latest.balance
                else:
                    date_nw -= latest.balance
        net_worth_history.append({
            "date": dt.isoformat(),
            "balance": date_nw
        })
    
    # Create mock balance objects for calculate_performance_metrics
    class MockBalance:
        def __init__(self, d, b):
            self.balance_date = datetime.strptime(d, '%Y-%m-%d').date() if isinstance(d, str) else d
            self.balance = b
    
    mock_balances = [MockBalance(h['date'], h['balance']) for h in net_worth_history]
    
    # Calculate overall performance for the period
    overall_performance = calculate_performance_metrics(mock_balances, net_worth, period)
    
    # Calculate per-account performance
    account_performance = []
    for account in accounts:
        if not account.balances:
            continue
        current_balance = max(account.balances, key=lambda b: b.balance_date).balance
        perf = calculate_performance_metrics(list(account.balances), current_balance, period)
        account_performance.append({
            "id": account.id,
            "name": account.name,
            "is_asset": account.is_asset,
            "current_balance": current_balance,
            **perf
        })
    
    return JSONResponse({
        "performance": overall_performance,
        "account_performance": account_performance,
        "current_net_worth": net_worth
    })


@router.get("/tools/networth/account/{account_id}")
async def get_account_details(
    request: Request,
    account_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed account information including all balances."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user.id
    ).first()
    
    if not account:
        return JSONResponse({"error": "Account not found"}, status_code=404)
    
    balances = [
        {
            "id": b.id,
            "date": b.balance_date.isoformat(),
            "balance": b.balance,
            "notes": b.notes
        }
        for b in sorted(account.balances, key=lambda b: b.balance_date, reverse=True)
    ]
    
    contribution = None
    if account.contribution:
        contribution = {
            "amount": account.contribution.amount,
            "frequency": account.contribution.frequency,
            "employer_match": account.contribution.employer_match,
            "employer_match_type": account.contribution.employer_match_type,
            "employer_match_limit": account.contribution.employer_match_limit,
            "expected_return": account.contribution.expected_return,
            "interest_rate": account.contribution.interest_rate,
            "stocks_pct": account.contribution.stocks_pct,
            "bonds_pct": account.contribution.bonds_pct,
            "cash_pct": account.contribution.cash_pct,
            "notes": account.contribution.notes
        }
    
    return JSONResponse({
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "is_asset": account.is_asset,
        "institution": account.institution,
        "notes": account.notes,
        "balances": balances,
        "contribution": contribution
    })


# =============================================================================
# Monte Carlo Simulation Routes
# =============================================================================

# Historical inflation rates (1928-2023) - CPI annual changes
HISTORICAL_INFLATION = [
    -0.0097, 0.0020, -0.0603, -0.0952, -0.1027, 0.0076, 0.0151, 0.0299,
    0.0121, 0.0283, -0.0278, 0.0000, 0.0096, 0.0972, 0.0929, 0.0316,
    0.0211, 0.0229, 0.1440, 0.0765, 0.0701, -0.0195, 0.0593, 0.0600,
    0.0086, 0.0062, -0.0050, 0.0037, 0.0303, 0.0290, 0.0176, 0.0146,
    0.0107, 0.0122, 0.0111, 0.0124, 0.0165, 0.0292, 0.0287, 0.0410,
    0.0480, 0.0546, 0.0332, 0.0341, 0.0870, 0.1234, 0.0694, 0.0486,
    0.0667, 0.0900, 0.1331, 0.1258, 0.0894, 0.0380, 0.0379, 0.0111,
    0.0435, 0.0441, 0.0465, 0.0613, 0.0309, 0.0290, 0.0275, 0.0267,
    0.0254, 0.0332, 0.0170, 0.0160, 0.0270, 0.0339, 0.0016, 0.0238,
    0.0159, 0.0300, 0.0173, 0.0150, 0.0076, 0.0291, 0.0230, 0.0121,
    0.0140, 0.0240, 0.0180, 0.0700, 0.0650, 0.0340  # Through 2023
]


def calculate_rolling_period_returns(returns: np.ndarray, period_years: int) -> dict:
    """
    Calculate rolling period statistics for historical returns.
    
    For a given investment period (e.g., 10, 15, 20, 25, 30 years),
    calculates all possible rolling period returns and their statistics.
    
    Args:
        returns: Array of annual returns
        period_years: Investment period length in years
        
    Returns:
        Dictionary with mean, std, min, max, and all rolling returns
    """
    if len(returns) < period_years:
        # Not enough data, return simple mean
        return {
            "mean": float(np.mean(returns)),
            "std": float(np.std(returns)),
            "min": float(np.min(returns)),
            "max": float(np.max(returns)),
            "rolling_cagrs": []
        }
    
    # Calculate CAGR for each rolling period
    rolling_cagrs = []
    for i in range(len(returns) - period_years + 1):
        period_returns = returns[i:i + period_years]
        # Calculate CAGR: (1+r1)(1+r2)...(1+rn)^(1/n) - 1
        cumulative = np.prod(1 + period_returns)
        cagr = cumulative ** (1 / period_years) - 1
        rolling_cagrs.append(cagr)
    
    rolling_cagrs = np.array(rolling_cagrs)
    
    return {
        "mean": float(np.mean(rolling_cagrs)),
        "std": float(np.std(rolling_cagrs)),
        "min": float(np.min(rolling_cagrs)),
        "max": float(np.max(rolling_cagrs)),
        "rolling_cagrs": rolling_cagrs.tolist()
    }


def get_period_adjusted_returns(projection_years: int) -> dict:
    """
    Get period-appropriate expected return statistics for stocks, bonds, and cash.
    
    Historical data shows that longer investment periods typically have
    less volatile outcomes - the range of possible returns narrows.
    
    Args:
        projection_years: Number of years to project
        
    Returns:
        Dictionary with period-adjusted statistics for each asset class
    """
    stock_returns = np.array(HISTORICAL_RETURNS["stocks"])
    bond_returns = np.array(HISTORICAL_RETURNS["bonds"])
    cash_returns = np.array(HISTORICAL_RETURNS["cash"])
    
    # Round projection years to nearest standard period
    if projection_years <= 10:
        period = 10
    elif projection_years <= 15:
        period = 15
    elif projection_years <= 20:
        period = 20
    elif projection_years <= 25:
        period = 25
    else:
        period = 30
    
    return {
        "projection_years": projection_years,
        "period_used": period,
        "stocks": calculate_rolling_period_returns(stock_returns, period),
        "bonds": calculate_rolling_period_returns(bond_returns, period),
        "cash": calculate_rolling_period_returns(cash_returns, period)
    }


def run_monte_carlo_simulation(
    accounts_data: List[dict], 
    years: int = 30, 
    num_simulations: int = 1000,
    include_inflation: bool = True,
    show_todays_dollars: bool = True,
    # Withdrawal parameters for FIRE planning
    include_withdrawals: bool = False,
    withdrawal_method: str = "fixed_swr",
    withdrawal_rate: float = 0.04,
    annual_withdrawal: Optional[float] = None,
    upper_guardrail: float = 0.05,
    lower_guardrail: float = 0.03,
    guardrail_adjustment: float = 0.10,
    withdrawal_floor: float = 0,
    withdrawal_ceiling: float = 0
) -> dict:
    """
    Run Monte Carlo simulation for investment projections.
    
    Uses historical returns data for stocks, bonds, and cash to simulate
    potential portfolio outcomes over time. Employs "block bootstrap" method
    that samples consecutive historical periods to preserve year-to-year
    correlations and momentum effects in market data.
    
    Period-appropriate behavior:
    - Uses rolling historical period statistics for the given projection length
    - Samples from consecutive historical sequences (block bootstrap)
    - Maintains correlation between stocks, bonds, cash, and inflation
    
    Args:
        accounts_data: List of account configurations with current balance,
                      contributions, and portfolio allocation
        years: Number of years to project
        num_simulations: Number of simulation runs
        include_inflation: Whether to factor in historical inflation
        show_todays_dollars: If True, discount future values by inflation
        
    Returns:
        Dictionary with simulation results including percentiles and distributions
    """
    # Get period-adjusted expected return statistics for context
    period_stats = get_period_adjusted_returns(years)
    
    results = {
        "simulations": [],
        "percentiles": {},
        "percentiles_nominal": {},  # Before inflation adjustment
        "account_results": {},
        "years": years,
        "num_simulations": num_simulations,
        "inflation_adjusted": show_todays_dollars,
        "period_statistics": {
            "period_used": period_stats["period_used"],
            "stocks": {
                "historical_mean_cagr": round(period_stats["stocks"]["mean"] * 100, 2),
                "historical_min_cagr": round(period_stats["stocks"]["min"] * 100, 2),
                "historical_max_cagr": round(period_stats["stocks"]["max"] * 100, 2),
            },
            "bonds": {
                "historical_mean_cagr": round(period_stats["bonds"]["mean"] * 100, 2),
                "historical_min_cagr": round(period_stats["bonds"]["min"] * 100, 2),
                "historical_max_cagr": round(period_stats["bonds"]["max"] * 100, 2),
            },
            "cash": {
                "historical_mean_cagr": round(period_stats["cash"]["mean"] * 100, 2),
            }
        }
    }
    
    # Get historical returns
    stock_returns = np.array(HISTORICAL_RETURNS["stocks"])
    bond_returns = np.array(HISTORICAL_RETURNS["bonds"])
    cash_returns = np.array(HISTORICAL_RETURNS["cash"])
    inflation_rates = np.array(HISTORICAL_INFLATION)
    num_historical_years = len(stock_returns)
    
    # Initialize tracking arrays
    all_final_values = []
    all_final_values_nominal = []  # Before inflation adjustment
    all_paths = []
    all_paths_nominal = []
    all_twrr = []  # Time-weighted rates of return
    all_total_contributions = []  # Track total contributions per simulation
    account_final_values = {acc["id"]: [] for acc in accounts_data if acc["is_asset"]}
    
    # Calculate total annual contributions for TWRR tracking
    total_annual_contributions = sum(
        acc.get("contribution_monthly", 0) * 12 
        for acc in accounts_data if acc.get("is_asset", False)
    )
    
    # Track success rate for FIRE simulations
    all_sim_success = []  # Track if each simulation succeeded (portfolio didn't deplete)
    all_total_withdrawals = []  # Track total withdrawals per simulation
    
    # Run simulations using block bootstrap method
    for sim in range(num_simulations):
        # Initialize account balances for this simulation
        sim_accounts = {}
        sim_path = [0]  # Track total net worth path
        sim_path_nominal = [0]
        cumulative_inflation = 1.0  # For converting to today's dollars
        sim_total_contributions = 0  # Track contributions for this simulation
        sim_total_withdrawals = 0  # Track withdrawals for this simulation
        
        for acc in accounts_data:
            sim_accounts[acc["id"]] = {
                "balance": acc["current_balance"],
                "is_asset": acc["is_asset"],
                "contribution_monthly": acc.get("contribution_monthly", 0),
                "stocks_pct": acc.get("stocks_pct", 80) / 100,
                "bonds_pct": acc.get("bonds_pct", 15) / 100,
                "cash_pct": acc.get("cash_pct", 5) / 100,
                "interest_rate": acc.get("interest_rate", 0) / 100 / 12,  # Monthly
                "path": [acc["current_balance"]]
            }
        
        initial_nw = sum(
            acc["balance"] if acc["is_asset"] else -acc["balance"]
            for acc in sim_accounts.values()
        )
        sim_path[0] = initial_nw
        sim_path_nominal[0] = initial_nw
        
        # Block bootstrap: select a random starting year and use consecutive years
        # This preserves historical correlations between asset classes and momentum
        # For each "block", we pick a random starting point and use sequential years
        block_size = min(years, 10)  # Use blocks of up to 10 years
        
        year_idx = 0
        while year_idx < years:
            # Pick a random starting point in history
            max_start = num_historical_years - block_size
            block_start = random.randint(0, max(0, max_start))
            
            # Use consecutive years from this starting point
            for block_year in range(block_size):
                if year_idx >= years:
                    break
                    
                hist_idx = (block_start + block_year) % num_historical_years
                yr_stock = stock_returns[hist_idx]
                yr_bond = bond_returns[hist_idx]
                yr_cash = cash_returns[hist_idx]
                
                # Get inflation for this year (use same historical index for correlation)
                inf_idx = min(hist_idx, len(inflation_rates) - 1)
                yr_inflation = inflation_rates[inf_idx] if include_inflation else 0
                cumulative_inflation *= (1 + yr_inflation)
                
                for acc_id, acc in sim_accounts.items():
                    if acc["is_asset"]:
                        # Apply weighted return based on portfolio allocation
                        portfolio_return = (
                            acc["stocks_pct"] * yr_stock +
                            acc["bonds_pct"] * yr_bond +
                            acc["cash_pct"] * yr_cash
                        )
                        # Apply annual return + 12 months of contributions
                        acc["balance"] *= (1 + portfolio_return)
                        annual_contrib = acc["contribution_monthly"] * 12
                        acc["balance"] += annual_contrib
                        sim_total_contributions += annual_contrib
                    else:
                        # Liability - apply interest and payments
                        for month in range(12):
                            acc["balance"] *= (1 + acc["interest_rate"])
                            acc["balance"] = max(0, acc["balance"] - acc["contribution_monthly"])
                    
                    acc["path"].append(acc["balance"])
                
                # Calculate net worth at end of year (before withdrawals)
                year_nw_nominal = sum(
                    acc["balance"] if acc["is_asset"] else -acc["balance"]
                    for acc in sim_accounts.values()
                )
                
                # Apply withdrawals if enabled
                if include_withdrawals and year_nw_nominal > 0:
                    # Calculate this year's withdrawal based on method
                    year_withdrawal = 0
                    
                    if withdrawal_method == "fixed_swr":
                        # Fixed percentage of initial portfolio, adjusted for inflation
                        if annual_withdrawal is not None:
                            year_withdrawal = annual_withdrawal * cumulative_inflation
                        else:
                            year_withdrawal = initial_nw * withdrawal_rate * cumulative_inflation
                    
                    elif withdrawal_method == "variable_pct":
                        # VPW: Withdraw based on remaining years
                        remaining_years = max(1, years - year_idx)
                        vpw_rate = 1 / remaining_years
                        year_withdrawal = year_nw_nominal * vpw_rate
                    
                    elif withdrawal_method == "guardrails":
                        # Guyton-Klinger guardrails
                        if annual_withdrawal is not None:
                            base_withdrawal = annual_withdrawal * cumulative_inflation
                        else:
                            base_withdrawal = initial_nw * withdrawal_rate * cumulative_inflation
                        
                        current_rate = base_withdrawal / year_nw_nominal if year_nw_nominal > 0 else 0
                        
                        if current_rate > upper_guardrail:
                            # Portfolio shrunk too much - reduce spending
                            year_withdrawal = base_withdrawal * (1 - guardrail_adjustment)
                        elif current_rate < lower_guardrail:
                            # Portfolio grew - can increase spending
                            year_withdrawal = base_withdrawal * (1 + guardrail_adjustment)
                        else:
                            year_withdrawal = base_withdrawal
                    
                    elif withdrawal_method == "floor_ceiling":
                        # Floor and ceiling approach
                        if annual_withdrawal is not None:
                            base_withdrawal = annual_withdrawal * cumulative_inflation
                        else:
                            base_withdrawal = year_nw_nominal * withdrawal_rate
                        
                        # Apply floor and ceiling (inflation-adjusted)
                        adj_floor = withdrawal_floor * cumulative_inflation if withdrawal_floor > 0 else 0
                        adj_ceiling = withdrawal_ceiling * cumulative_inflation if withdrawal_ceiling > 0 else float('inf')
                        
                        year_withdrawal = max(adj_floor, min(base_withdrawal, adj_ceiling))
                    
                    # Distribute withdrawal proportionally across asset accounts
                    total_assets = sum(acc["balance"] for acc in sim_accounts.values() if acc["is_asset"])
                    if total_assets > 0:
                        for acc_id, acc in sim_accounts.items():
                            if acc["is_asset"]:
                                acc_share = acc["balance"] / total_assets
                                withdrawal_from_acc = min(acc["balance"], year_withdrawal * acc_share)
                                acc["balance"] -= withdrawal_from_acc
                    
                    sim_total_withdrawals += year_withdrawal
                    
                    # Recalculate net worth after withdrawals
                    year_nw_nominal = sum(
                        acc["balance"] if acc["is_asset"] else -acc["balance"]
                        for acc in sim_accounts.values()
                    )
                # Convert to today's dollars if requested
                year_nw_real = year_nw_nominal / cumulative_inflation if show_todays_dollars else year_nw_nominal
                
                sim_path.append(year_nw_real)
                sim_path_nominal.append(year_nw_nominal)
                year_idx += 1
        
        # Record final values
        final_nw = sim_path[-1]
        final_nw_nominal = sim_path_nominal[-1]
        all_final_values.append(final_nw)
        all_final_values_nominal.append(final_nw_nominal)
        all_paths.append(sim_path)
        all_paths_nominal.append(sim_path_nominal)
        all_total_contributions.append(sim_total_contributions)
        all_total_withdrawals.append(sim_total_withdrawals)
        
        # Track success for FIRE simulations (portfolio didn't run out)
        sim_succeeded = final_nw_nominal > 0
        all_sim_success.append(sim_succeeded)
        
        # Calculate Time-Weighted Rate of Return (TWRR) for this simulation
        # TWRR = (Ending Value - Total Contributions) / Starting Value - 1
        # This gives the pure investment return excluding the effect of deposits
        if initial_nw > 0:
            investment_gain = final_nw_nominal - initial_nw - sim_total_contributions
            total_twrr = investment_gain / initial_nw
            # Annualize: (1 + TWRR)^(1/years) - 1
            annualized_twrr = (pow(1 + total_twrr, 1 / years) - 1) if years > 0 else 0
            all_twrr.append(annualized_twrr)
        else:
            all_twrr.append(0)
        
        for acc_id, acc in sim_accounts.items():
            if acc["is_asset"]:
                # Adjust for inflation if needed
                adj_balance = acc["balance"] / cumulative_inflation if show_todays_dollars else acc["balance"]
                account_final_values[acc_id].append(adj_balance)
    
    # Calculate percentiles (inflation-adjusted if enabled)
    all_final_values = np.array(all_final_values)
    results["percentiles"] = {
        "p10": float(np.percentile(all_final_values, 10)),
        "p25": float(np.percentile(all_final_values, 25)),
        "p50": float(np.percentile(all_final_values, 50)),
        "p75": float(np.percentile(all_final_values, 75)),
        "p90": float(np.percentile(all_final_values, 90)),
        "mean": float(np.mean(all_final_values)),
        "std": float(np.std(all_final_values)),
        "min": float(np.min(all_final_values)),
        "max": float(np.max(all_final_values))
    }
    
    # Also provide nominal values for comparison
    all_final_values_nom = np.array(all_final_values_nominal)
    results["percentiles_nominal"] = {
        "p10": float(np.percentile(all_final_values_nom, 10)),
        "p25": float(np.percentile(all_final_values_nom, 25)),
        "p50": float(np.percentile(all_final_values_nom, 50)),
        "p75": float(np.percentile(all_final_values_nom, 75)),
        "p90": float(np.percentile(all_final_values_nom, 90)),
        "mean": float(np.mean(all_final_values_nom)),
    }
    
    # Time-Weighted Rate of Return (TWRR) statistics
    all_twrr_arr = np.array(all_twrr)
    all_contributions_arr = np.array(all_total_contributions)
    initial_value = all_paths[0][0] if all_paths else 0
    
    results["twrr"] = {
        "p10": float(np.percentile(all_twrr_arr, 10) * 100),  # As percentage
        "p25": float(np.percentile(all_twrr_arr, 25) * 100),
        "p50": float(np.percentile(all_twrr_arr, 50) * 100),  # Median
        "p75": float(np.percentile(all_twrr_arr, 75) * 100),
        "p90": float(np.percentile(all_twrr_arr, 90) * 100),
        "mean": float(np.mean(all_twrr_arr) * 100),
        "std": float(np.std(all_twrr_arr) * 100),
    }
    
    # Contribution summary
    results["contributions"] = {
        "total_per_simulation": float(np.mean(all_contributions_arr)),
        "annual_rate": float(total_annual_contributions),
        "initial_value": float(initial_value),
    }
    
    # FIRE / Withdrawal statistics
    if include_withdrawals:
        success_count = sum(all_sim_success)
        success_rate = (success_count / num_simulations) * 100 if num_simulations > 0 else 0
        all_withdrawals_arr = np.array(all_total_withdrawals)
        
        results["fire_success_rate"] = float(success_rate)
        results["fire_statistics"] = {
            "success_rate": float(success_rate),
            "success_count": int(success_count),
            "failure_count": int(num_simulations - success_count),
            "total_withdrawals_mean": float(np.mean(all_withdrawals_arr)),
            "total_withdrawals_median": float(np.median(all_withdrawals_arr)),
            "annual_withdrawal_avg": float(np.mean(all_withdrawals_arr) / years) if years > 0 else 0,
            "withdrawal_method": withdrawal_method,
        }
    
    # Calculate path percentiles for chart
    all_paths = np.array(all_paths)
    results["path_percentiles"] = {
        "years": list(range(years + 1)),
        "p10": [float(np.percentile(all_paths[:, y], 10)) for y in range(years + 1)],
        "p25": [float(np.percentile(all_paths[:, y], 25)) for y in range(years + 1)],
        "p50": [float(np.percentile(all_paths[:, y], 50)) for y in range(years + 1)],
        "p75": [float(np.percentile(all_paths[:, y], 75)) for y in range(years + 1)],
        "p90": [float(np.percentile(all_paths[:, y], 90)) for y in range(years + 1)],
    }
    
    # Per-account results
    for acc_id, values in account_final_values.items():
        if values:
            values_arr = np.array(values)
            results["account_results"][acc_id] = {
                "p10": float(np.percentile(values_arr, 10)),
                "p25": float(np.percentile(values_arr, 25)),
                "p50": float(np.percentile(values_arr, 50)),
                "p75": float(np.percentile(values_arr, 75)),
                "p90": float(np.percentile(values_arr, 90)),
                "mean": float(np.mean(values_arr)),
            }
    
    return results


class MonteCarloRequest(BaseModel):
    """
    Request model for running Monte Carlo simulation.
    
    Parameters:
        years: Number of years to project (default 30)
        num_simulations: Number of simulations to run (more = higher precision, default 1000)
        show_todays_dollars: If True, results are adjusted for inflation to show
                            purchasing power in today's dollars (default True)
        include_withdrawals: If True, simulate retirement withdrawals (default False)
        withdrawal_method: Strategy for withdrawals (fixed_swr, variable_pct, guardrails, floor_ceiling)
        withdrawal_rate: Base withdrawal rate as decimal (default 0.04 = 4%)
        annual_withdrawal: Fixed annual withdrawal amount (optional, overrides rate)
        upper_guardrail: Upper guardrail rate for Guyton-Klinger (default 0.05)
        lower_guardrail: Lower guardrail rate for Guyton-Klinger (default 0.03)
        guardrail_adjustment: Adjustment percentage for guardrails (default 0.10)
        withdrawal_floor: Minimum annual withdrawal for floor/ceiling (default 0)
        withdrawal_ceiling: Maximum annual withdrawal for floor/ceiling (default 0 = no limit)
    """
    years: int = 30
    num_simulations: int = 1000
    show_todays_dollars: bool = True
    # Withdrawal parameters
    include_withdrawals: bool = False
    withdrawal_method: str = "fixed_swr"
    withdrawal_rate: float = 0.04
    annual_withdrawal: Optional[float] = None
    upper_guardrail: float = 0.05
    lower_guardrail: float = 0.03
    guardrail_adjustment: float = 0.10
    withdrawal_floor: float = 0
    withdrawal_ceiling: float = 0


@router.post("/tools/montecarlo/run")
async def run_montecarlo(
    request: Request,
    body: MonteCarloRequest,
    db: Session = Depends(get_db)
):
    """
    Run Monte Carlo simulation for investment projections.
    
    Uses historical returns (1928-2023) for stocks, bonds, and cash,
    along with historical inflation rates to simulate thousands of
    possible portfolio outcomes.
    
    The simulation randomly selects historical years and applies those
    returns to your portfolio based on your asset allocation.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Get all active accounts with contributions
    accounts = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_active == True
    ).all()
    
    if not accounts:
        return JSONResponse({"error": "No accounts found"}, status_code=400)
    
    # Prepare account data for simulation
    accounts_data = []
    for acc in accounts:
        latest_balance = 0
        if acc.balances:
            latest = max(acc.balances, key=lambda b: b.balance_date)
            latest_balance = latest.balance
        
        contrib = acc.contribution
        
        # Calculate contribution amount - explicitly handle 0 values
        contrib_amount = 0
        if contrib and contrib.amount is not None:
            contrib_amount = contrib.amount
        
        # Frequency multiplier to convert to monthly
        freq_multiplier = 1  # default monthly
        if contrib:
            freq = contrib.frequency or "monthly"
            if freq == "annually":
                freq_multiplier = 12
            elif freq == "quarterly":
                freq_multiplier = 4
            elif freq == "monthly":
                freq_multiplier = 1
            elif freq == "semi-monthly":
                freq_multiplier = 2
            elif freq == "bi-weekly":
                freq_multiplier = 2.17
            elif freq == "weekly":
                freq_multiplier = 4.33
        
        monthly_contribution = (contrib_amount * freq_multiplier) / 12
        
        # Get portfolio allocation - explicitly allow 0 values, only use defaults for None
        stocks_pct = 80  # default
        bonds_pct = 15   # default  
        cash_pct = 5     # default
        interest_rate = 0
        
        if contrib:
            if contrib.stocks_pct is not None:
                stocks_pct = contrib.stocks_pct
            if contrib.bonds_pct is not None:
                bonds_pct = contrib.bonds_pct
            if contrib.cash_pct is not None:
                cash_pct = contrib.cash_pct
            if contrib.interest_rate is not None:
                interest_rate = contrib.interest_rate
        
        accounts_data.append({
            "id": acc.id,
            "name": acc.name,
            "account_type": acc.account_type,
            "is_asset": acc.is_asset,
            "current_balance": latest_balance,
            "contribution_monthly": monthly_contribution,
            "stocks_pct": stocks_pct,
            "bonds_pct": bonds_pct,
            "cash_pct": cash_pct,
            "interest_rate": interest_rate
        })
    
    # Run simulation
    try:
        results = run_monte_carlo_simulation(
            accounts_data,
            years=body.years,
            num_simulations=body.num_simulations,
            include_inflation=True,
            show_todays_dollars=body.show_todays_dollars,
            # FIRE / Withdrawal parameters
            include_withdrawals=body.include_withdrawals,
            withdrawal_method=body.withdrawal_method,
            withdrawal_rate=body.withdrawal_rate,
            annual_withdrawal=body.annual_withdrawal,
            upper_guardrail=body.upper_guardrail,
            lower_guardrail=body.lower_guardrail,
            guardrail_adjustment=body.guardrail_adjustment,
            withdrawal_floor=body.withdrawal_floor,
            withdrawal_ceiling=body.withdrawal_ceiling
        )
        
        # Add tax analysis to results based on current and projected values
        tax_analysis = calculate_projected_tax_analysis(accounts_data, results)
        results["tax_analysis"] = tax_analysis
        
        dollars_type = "today's dollars" if body.show_todays_dollars else "future dollars"
        logger.info(f"Monte Carlo simulation completed: {body.num_simulations} sims over {body.years} years ({dollars_type})")
        return JSONResponse(results)
    except Exception as e:
        logger.error(f"Monte Carlo simulation error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


def calculate_projected_tax_analysis(accounts_data: List[dict], simulation_results: dict) -> dict:
    """
    Calculate tax analysis for projected portfolio values.
    
    Uses the median (p50) projected values to estimate future tax breakdown.
    
    Args:
        accounts_data: List of account data with account_type
        simulation_results: Results from Monte Carlo simulation with account_results
        
    Returns:
        Dictionary with current and projected tax breakdown
    """
    # Current totals by tax treatment
    current_tax_free = 0.0
    current_tax_deferred = 0.0
    current_taxable = 0.0
    current_partially_taxable = 0.0
    
    # Projected totals (using median p50)
    projected_tax_free = 0.0
    projected_tax_deferred = 0.0
    projected_taxable = 0.0
    projected_partially_taxable = 0.0
    
    account_results = simulation_results.get("account_results", {})
    
    for acc in accounts_data:
        if not acc["is_asset"]:
            continue
            
        acc_id = acc["id"]
        current_balance = acc["current_balance"]
        projected_balance = account_results.get(str(acc_id), {}).get("p50", current_balance) if acc_id in account_results else current_balance
        
        # Determine tax treatment
        treatment = TAX_TREATMENT.get(acc.get("account_type", ""), "taxable")
        
        if treatment == "tax_free":
            current_tax_free += current_balance
            projected_tax_free += projected_balance
        elif treatment == "tax_deferred":
            current_tax_deferred += current_balance
            projected_tax_deferred += projected_balance
        elif treatment == "partially_taxable":
            current_partially_taxable += current_balance
            projected_partially_taxable += projected_balance
        else:
            current_taxable += current_balance
            projected_taxable += projected_balance
    
    current_total = current_tax_free + current_tax_deferred + current_taxable + current_partially_taxable
    projected_total = projected_tax_free + projected_tax_deferred + projected_taxable + projected_partially_taxable
    
    return {
        "current": {
            "total": current_total,
            "tax_free": {
                "amount": current_tax_free,
                "percentage": (current_tax_free / current_total * 100) if current_total > 0 else 0
            },
            "tax_deferred": {
                "amount": current_tax_deferred,
                "percentage": (current_tax_deferred / current_total * 100) if current_total > 0 else 0
            },
            "taxable": {
                "amount": current_taxable,
                "percentage": (current_taxable / current_total * 100) if current_total > 0 else 0
            },
            "partially_taxable": {
                "amount": current_partially_taxable,
                "percentage": (current_partially_taxable / current_total * 100) if current_total > 0 else 0
            }
        },
        "projected": {
            "total": projected_total,
            "tax_free": {
                "amount": projected_tax_free,
                "percentage": (projected_tax_free / projected_total * 100) if projected_total > 0 else 0
            },
            "tax_deferred": {
                "amount": projected_tax_deferred,
                "percentage": (projected_tax_deferred / projected_total * 100) if projected_total > 0 else 0
            },
            "taxable": {
                "amount": projected_taxable,
                "percentage": (projected_taxable / projected_total * 100) if projected_total > 0 else 0
            },
            "partially_taxable": {
                "amount": projected_partially_taxable,
                "percentage": (projected_partially_taxable / projected_total * 100) if projected_total > 0 else 0
            }
        }
    }


class MonteCarloSaveRequest(BaseModel):
    """Request model for saving Monte Carlo scenario."""
    name: str
    years: int
    num_simulations: int
    results: dict


@router.post("/tools/montecarlo/save")
async def save_montecarlo_scenario(
    request: Request,
    body: MonteCarloSaveRequest,
    db: Session = Depends(get_db)
):
    """Save a Monte Carlo simulation scenario."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Check scenario limit (max 5 per user)
    existing_count = db.query(MonteCarloScenario).filter(
        MonteCarloScenario.user_id == user.id
    ).count()
    
    if existing_count >= MAX_SCENARIOS_PER_TYPE:
        logger.warning(f"User {user.username} hit Monte Carlo scenario limit ({MAX_SCENARIOS_PER_TYPE})")
        return JSONResponse({
            "error": f"Maximum of {MAX_SCENARIOS_PER_TYPE} saved scenarios allowed. Please delete an existing scenario first."
        }, status_code=400)
    
    try:
        # Get current account settings for snapshot
        accounts = db.query(Account).filter(
            Account.user_id == user.id,
            Account.is_active == True
        ).all()
        
        settings = []
        for acc in accounts:
            settings.append({
                "id": acc.id,
                "name": acc.name,
                "is_asset": acc.is_asset,
                "stocks_pct": acc.contribution.stocks_pct if acc.contribution else 80,
                "bonds_pct": acc.contribution.bonds_pct if acc.contribution else 15,
                "cash_pct": acc.contribution.cash_pct if acc.contribution else 5,
            })
        
        scenario = MonteCarloScenario(
            user_id=user.id,
            name=body.name,
            projection_years=body.years,
            num_simulations=body.num_simulations,
            settings_json=json.dumps(settings),
            results_json=json.dumps(body.results)
        )
        db.add(scenario)
        db.commit()
        db.refresh(scenario)
        
        logger.info(f"Monte Carlo scenario saved: {body.name} (ID: {scenario.id})")
        return JSONResponse({"success": True, "id": scenario.id})
    except Exception as e:
        logger.error(f"Error saving Monte Carlo scenario: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/tools/montecarlo/scenarios")
async def list_montecarlo_scenarios(request: Request, db: Session = Depends(get_db)):
    """List all saved Monte Carlo scenarios for current user."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    scenarios = db.query(MonteCarloScenario).filter(
        MonteCarloScenario.user_id == user.id
    ).order_by(MonteCarloScenario.created_at.desc()).all()
    
    return JSONResponse([{
        "id": s.id,
        "name": s.name,
        "years": s.projection_years,
        "simulations": s.num_simulations,
        "created_at": s.created_at.isoformat()
    } for s in scenarios])


@router.get("/tools/montecarlo/load/{scenario_id}")
async def load_montecarlo_scenario(
    request: Request,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """Load a saved Monte Carlo scenario."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    scenario = db.query(MonteCarloScenario).filter(
        MonteCarloScenario.id == scenario_id,
        MonteCarloScenario.user_id == user.id
    ).first()
    
    if not scenario:
        return JSONResponse({"error": "Scenario not found"}, status_code=404)
    
    return JSONResponse({
        "id": scenario.id,
        "name": scenario.name,
        "years": scenario.projection_years,
        "simulations": scenario.num_simulations,
        "settings": json.loads(scenario.settings_json) if scenario.settings_json else [],
        "results": json.loads(scenario.results_json) if scenario.results_json else {}
    })


@router.delete("/tools/montecarlo/delete/{scenario_id}")
async def delete_montecarlo_scenario(
    request: Request,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """Delete a Monte Carlo scenario."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    scenario = db.query(MonteCarloScenario).filter(
        MonteCarloScenario.id == scenario_id,
        MonteCarloScenario.user_id == user.id
    ).first()
    
    if scenario:
        db.delete(scenario)
        db.commit()
        logger.info(f"Monte Carlo scenario deleted: {scenario.name}")
        return JSONResponse({"success": True})
    
    return JSONResponse({"error": "Scenario not found"}, status_code=404)


# =============================================================================
# Net Worth CSV Upload/Download
# =============================================================================

@router.get("/tools/networth/csv-template")
async def download_networth_csv_template(request: Request, db: Session = Depends(get_db)):
    """Download a CSV template for net worth data import."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    # Create template CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "account_name",
        "account_type",
        "is_asset",
        "institution",
        "balance_date",
        "balance",
        "notes"
    ])
    
    # Write example rows
    writer.writerow([
        "401k - Fidelity",
        "401k",
        "true",
        "Fidelity",
        "2024-01-15",
        "125000.00",
        "End of year balance"
    ])
    writer.writerow([
        "Savings Account",
        "savings",
        "true",
        "Chase",
        "2024-01-15",
        "15000.00",
        ""
    ])
    writer.writerow([
        "Mortgage",
        "mortgage",
        "false",
        "Wells Fargo",
        "2024-01-15",
        "320000.00",
        "Principal balance"
    ])
    
    output.seek(0)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=networth_upload_template.csv"}
    )


@router.post("/tools/networth/csv-upload")
async def upload_networth_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload CSV file to bulk import net worth data."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        contents = await csv_file.read()
        decoded = contents.decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        
        # Track what was created
        accounts_created = []
        balances_added = 0
        errors = []
        
        # Cache for account lookups
        account_cache = {}
        
        for row_num, row in enumerate(reader, start=2):
            try:
                account_name = row.get("account_name", "").strip()
                account_type = row.get("account_type", "").strip()
                is_asset_str = row.get("is_asset", "true").strip().lower()
                institution = row.get("institution", "").strip() or None
                balance_date_str = row.get("balance_date", "").strip()
                balance_str = row.get("balance", "0").strip()
                notes = row.get("notes", "").strip() or None
                
                if not account_name:
                    errors.append(f"Row {row_num}: Missing account_name")
                    continue
                
                if not balance_date_str:
                    errors.append(f"Row {row_num}: Missing balance_date")
                    continue
                
                # Parse values
                is_asset = is_asset_str in ("true", "1", "yes", "asset")
                balance = float(balance_str.replace(",", "").replace("$", ""))
                balance_date = datetime.strptime(balance_date_str, "%Y-%m-%d").date()
                
                # Find or create account
                cache_key = f"{account_name}_{account_type}_{is_asset}"
                if cache_key in account_cache:
                    account = account_cache[cache_key]
                else:
                    account = db.query(Account).filter(
                        Account.user_id == user.id,
                        Account.name == account_name,
                        Account.account_type == account_type
                    ).first()
                    
                    if not account:
                        account = Account(
                            user_id=user.id,
                            name=account_name,
                            account_type=account_type,
                            is_asset=is_asset,
                            institution=institution
                        )
                        db.add(account)
                        db.flush()
                        accounts_created.append(account_name)
                    
                    account_cache[cache_key] = account
                
                # Add balance entry
                balance_entry = AccountBalance(
                    account_id=account.id,
                    balance_date=balance_date,
                    balance=balance,
                    notes=notes
                )
                db.add(balance_entry)
                balances_added += 1
                
            except ValueError as ve:
                errors.append(f"Row {row_num}: {str(ve)}")
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        db.commit()
        
        logger.info(f"Net worth CSV upload: {len(accounts_created)} accounts created, {balances_added} balances added")
        
        return JSONResponse({
            "success": True,
            "accounts_created": accounts_created,
            "balances_added": balances_added,
            "errors": errors[:10]  # Limit error messages
        })
        
    except Exception as e:
        logger.error(f"Net worth CSV upload error: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/tools/networth/csv-export")
async def export_networth_csv(request: Request, db: Session = Depends(get_db)):
    """Export all net worth data as CSV."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    accounts = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_active == True
    ).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "account_name",
        "account_type",
        "is_asset",
        "institution",
        "balance_date",
        "balance",
        "notes"
    ])
    
    # Write all balance entries
    for account in accounts:
        for balance in sorted(account.balances, key=lambda b: b.balance_date):
            writer.writerow([
                account.name,
                account.account_type,
                "true" if account.is_asset else "false",
                account.institution or "",
                balance.balance_date.strftime("%Y-%m-%d"),
                f"{balance.balance:.2f}",
                balance.notes or ""
            ])
    
    output.seek(0)
    
    logger.info(f"Net worth CSV exported for user {user.username}")
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=networth_export_{date.today().isoformat()}.csv"}
    )


# =============================================================================
# FIRE Planning Calculator
# =============================================================================

class FIRERequest(BaseModel):
    """
    Request model for FIRE (Financial Independence, Retire Early) calculations.
    
    This comprehensive model captures all inputs needed to calculate:
    - FI Number (target portfolio value)
    - Years to FI based on actual account data
    - Monte Carlo success rates for both accumulation and withdrawal phases
    - Multiple FIRE approach comparisons
    """
    # Personal profile
    current_age: int = 30
    target_retirement_age: int = 50
    life_expectancy: int = 90
    
    # Expense inputs
    annual_expenses: float = 50000
    retirement_expenses: float = 40000  # Often lower than pre-retirement
    
    # Other income sources
    social_security_monthly: float = 0  # Expected SS at 67
    social_security_start_age: int = 67
    pension_monthly: float = 0
    pension_start_age: int = 65
    
    # Assumptions
    inflation_rate: float = 3.0  # As percentage
    
    # FIRE type and withdrawal strategy
    fire_type: str = "regular"  # regular, lean, fat, coast, barista
    withdrawal_method: str = "fixed_swr"
    withdrawal_rate: float = 4.0  # As percentage
    
    # Withdrawal strategy parameters
    upper_guardrail: float = 5.0
    lower_guardrail: float = 3.0
    guardrail_adjustment: float = 10.0
    withdrawal_floor: float = 30000
    withdrawal_ceiling: float = 80000
    
    # Barista FIRE - part-time income
    part_time_income: float = 0
    part_time_years: int = 10
    
    # Monte Carlo settings
    num_simulations: int = 1000
    include_monte_carlo: bool = True


def calculate_fi_number(
    retirement_expenses: float,
    withdrawal_rate: float,
    fire_type: str,
    current_age: int,
    life_expectancy: int,
    target_retirement_age: int,
    inflation_rate: float,
    social_security_annual: float = 0,
    pension_annual: float = 0
) -> dict:
    """
    Calculate the FI (Financial Independence) number based on FIRE type and withdrawal strategy.
    
    The FI number represents the portfolio value needed to sustain retirement withdrawals
    indefinitely (or until life expectancy for some methods).
    
    Args:
        retirement_expenses: Annual expenses in retirement
        withdrawal_rate: Safe withdrawal rate as decimal (e.g., 0.04)
        fire_type: Type of FIRE strategy (regular, lean, fat, coast, barista)
        current_age: Current age
        life_expectancy: Expected lifespan
        target_retirement_age: Age to retire
        inflation_rate: Expected annual inflation as decimal
        social_security_annual: Annual Social Security income
        pension_annual: Annual pension income
        
    Returns:
        Dictionary with FI number and calculation details
    """
    # Calculate income from other sources (reduces portfolio needs)
    # These typically don't start until specific ages, so calculate effective value
    other_income = social_security_annual + pension_annual
    
    # Portfolio must cover expenses NOT covered by other income
    expenses_from_portfolio = max(0, retirement_expenses - other_income)
    
    # Base FI number using traditional formula
    if withdrawal_rate > 0:
        base_fi_number = expenses_from_portfolio / withdrawal_rate
    else:
        base_fi_number = expenses_from_portfolio * 25  # Fallback to 4% rule
    
    # Adjust based on FIRE type
    years_to_retirement = target_retirement_age - current_age
    retirement_years = life_expectancy - target_retirement_age
    
    fi_details = {
        "base_fi_number": base_fi_number,
        "adjustment_factor": 1.0,
        "adjusted_fi_number": base_fi_number,
        "fire_type": fire_type,
        "withdrawal_rate": withdrawal_rate * 100,
        "expenses_from_portfolio": expenses_from_portfolio,
        "other_income_annual": other_income,
    }
    
    if fire_type == "lean":
        # Lean FIRE - minimal expenses, typically 60-70% of regular
        fi_details["adjustment_factor"] = 0.7
        fi_details["adjusted_fi_number"] = base_fi_number * 0.7
        fi_details["description"] = "Minimal lifestyle - requires strict budgeting"
        
    elif fire_type == "fat":
        # Fat FIRE - comfortable/luxury lifestyle, typically 150-200% of regular
        fi_details["adjustment_factor"] = 1.5
        fi_details["adjusted_fi_number"] = base_fi_number * 1.5
        fi_details["description"] = "Comfortable lifestyle with room for luxuries"
        
    elif fire_type == "coast":
        # Coast FIRE - save enough now that it will grow to FI number by traditional retirement
        # Calculate what you need NOW to coast to full FI by age 65
        coast_target_age = 65
        coast_years = coast_target_age - current_age
        expected_growth = 0.07  # Assume 7% real growth
        
        if coast_years > 0:
            # PV = FV / (1 + r)^n
            coast_fi_number = base_fi_number / ((1 + expected_growth) ** coast_years)
            fi_details["adjusted_fi_number"] = coast_fi_number
            fi_details["adjustment_factor"] = coast_fi_number / base_fi_number if base_fi_number > 0 else 0
            fi_details["coast_target_age"] = coast_target_age
            fi_details["coast_years"] = coast_years
        fi_details["description"] = f"Save enough to let it grow to full FI by age {coast_target_age}"
        
    elif fire_type == "barista":
        # Barista FIRE - part-time work covers some expenses, need smaller portfolio
        fi_details["adjustment_factor"] = 0.7
        fi_details["adjusted_fi_number"] = base_fi_number * 0.7
        fi_details["description"] = "Part-time work covers 30% of expenses"
        
    else:  # regular
        fi_details["adjusted_fi_number"] = base_fi_number
        fi_details["description"] = "Traditional FIRE - full financial independence"
    
    return fi_details


def run_monte_carlo_fi_analysis(
    accounts_data: List[dict],
    fi_number: float,
    retirement_expenses: float,
    current_age: int,
    life_expectancy: int,
    withdrawal_rate: float = 0.04,
    withdrawal_method: str = "fixed_swr",
    num_simulations: int = 500,
    social_security_annual: float = 0,
    ss_start_age: int = 67,
    pension_annual: float = 0,
    pension_start_age: int = 65,
    upper_guardrail: float = 0.05,
    lower_guardrail: float = 0.03,
    guardrail_adjustment: float = 0.10,
    withdrawal_floor: float = 0,
    withdrawal_ceiling: float = 0
) -> dict:
    """
    Run Monte Carlo simulation to find when FI is achieved and project through life expectancy.
    
    This function:
    1. Simulates portfolio growth using historical returns based on actual portfolio allocations
    2. Identifies the year when portfolio reaches FI number (can sustain withdrawals)
    3. Projects through life expectancy to calculate success rates
    
    Returns comprehensive FIRE analysis including:
    - Expected years to FI (median from simulations)
    - Probability of reaching FI at various ages
    - Success rate for different retirement ages
    - Portfolio projection paths
    """
    # Get historical returns
    stock_returns = np.array(HISTORICAL_RETURNS["stocks"])
    bond_returns = np.array(HISTORICAL_RETURNS["bonds"])
    cash_returns = np.array(HISTORICAL_RETURNS["cash"])
    inflation_rates = np.array(HISTORICAL_INFLATION)
    num_historical_years = len(stock_returns)
    
    total_years = life_expectancy - current_age
    
    # Calculate weighted average portfolio allocation from accounts
    total_assets = sum(acc["current_balance"] for acc in accounts_data if acc["is_asset"])
    if total_assets > 0:
        avg_stocks_pct = sum(
            acc["current_balance"] * acc.get("stocks_pct", 80) / 100
            for acc in accounts_data if acc["is_asset"]
        ) / total_assets
        avg_bonds_pct = sum(
            acc["current_balance"] * acc.get("bonds_pct", 15) / 100
            for acc in accounts_data if acc["is_asset"]
        ) / total_assets
        avg_cash_pct = sum(
            acc["current_balance"] * acc.get("cash_pct", 5) / 100
            for acc in accounts_data if acc["is_asset"]
        ) / total_assets
    else:
        avg_stocks_pct, avg_bonds_pct, avg_cash_pct = 0.80, 0.15, 0.05
    
    # Results tracking
    all_fi_years = []  # Year when FI was reached in each simulation
    all_success = []  # Did the portfolio last through life expectancy?
    all_paths = []  # Portfolio value paths
    all_fi_ages = []  # Age when FI was reached
    
    # Initial portfolio value
    initial_value = sum(
        acc["current_balance"] if acc["is_asset"] else -acc["current_balance"]
        for acc in accounts_data
    )
    
    # Annual contributions (only during accumulation)
    total_annual_contributions = sum(
        acc.get("contribution_monthly", 0) * 12
        for acc in accounts_data if acc.get("is_asset", False)
    )
    
    for sim in range(num_simulations):
        # Initialize simulation
        portfolio_value = initial_value  # Nominal value
        sim_path_real = [portfolio_value]  # Real values (today's dollars)
        cumulative_inflation = 1.0
        fi_reached = False
        fi_year = None
        sim_succeeded = True
        
        # Block bootstrap for sequential years
        block_size = min(total_years, 10)
        year_idx = 0
        
        while year_idx < total_years:
            max_start = num_historical_years - block_size
            block_start = random.randint(0, max(0, max_start))
            
            for block_year in range(block_size):
                if year_idx >= total_years:
                    break
                
                hist_idx = (block_start + block_year) % num_historical_years
                yr_stock = stock_returns[hist_idx]
                yr_bond = bond_returns[hist_idx]
                yr_cash = cash_returns[hist_idx]
                
                inf_idx = min(hist_idx, len(inflation_rates) - 1)
                yr_inflation = inflation_rates[inf_idx]
                cumulative_inflation *= (1 + yr_inflation)
                
                current_year_age = current_age + year_idx
                
                # Check if FI has been reached (real portfolio value >= FI number in today's dollars)
                real_portfolio_value = portfolio_value / cumulative_inflation
                if not fi_reached and real_portfolio_value >= fi_number:
                    fi_reached = True
                    fi_year = year_idx
                
                # Apply returns using weighted portfolio allocation
                if not fi_reached:
                    # Accumulation phase - grow portfolio and add contributions
                    portfolio_return = (
                        avg_stocks_pct * yr_stock +
                        avg_bonds_pct * yr_bond +
                        avg_cash_pct * yr_cash
                    )
                    portfolio_value *= (1 + portfolio_return)
                    # Contributions grow with inflation (in real terms they stay constant)
                    portfolio_value += total_annual_contributions * cumulative_inflation
                    
                else:
                    # Withdrawal phase - apply returns then withdraw
                    portfolio_return = (
                        avg_stocks_pct * yr_stock +
                        avg_bonds_pct * yr_bond +
                        avg_cash_pct * yr_cash
                    )
                    portfolio_value *= (1 + portfolio_return)
                    
                    # Calculate other income for this year (inflation-adjusted)
                    other_income = 0
                    if ss_start_age > 0 and current_year_age >= ss_start_age:
                        other_income += social_security_annual * cumulative_inflation
                    if pension_start_age > 0 and current_year_age >= pension_start_age:
                        other_income += pension_annual * cumulative_inflation
                    
                    # Calculate withdrawal (in nominal terms)
                    year_withdrawal = 0
                    expenses_needed = retirement_expenses * cumulative_inflation - other_income
                    expenses_needed = max(0, expenses_needed)
                    
                    if withdrawal_method == "fixed_swr":
                        year_withdrawal = expenses_needed
                        
                    elif withdrawal_method == "variable_pct":
                        remaining_years = max(1, life_expectancy - current_year_age)
                        vpw_rate = 1 / remaining_years
                        year_withdrawal = min(portfolio_value * vpw_rate, expenses_needed * 1.5)
                        
                    elif withdrawal_method == "guardrails":
                        base_rate = expenses_needed / portfolio_value if portfolio_value > 0 else 0
                        if base_rate > upper_guardrail:
                            year_withdrawal = expenses_needed * (1 - guardrail_adjustment)
                        elif base_rate < lower_guardrail:
                            year_withdrawal = expenses_needed * (1 + guardrail_adjustment)
                        else:
                            year_withdrawal = expenses_needed
                            
                    elif withdrawal_method == "floor_ceiling":
                        adj_floor = withdrawal_floor * cumulative_inflation if withdrawal_floor > 0 else 0
                        adj_ceiling = withdrawal_ceiling * cumulative_inflation if withdrawal_ceiling > 0 else float('inf')
                        year_withdrawal = max(adj_floor, min(expenses_needed, adj_ceiling))
                    
                    portfolio_value -= max(0, year_withdrawal)
                
                # Check for depletion
                if portfolio_value <= 0:
                    sim_succeeded = False
                    portfolio_value = 0
                
                # Store real (today's dollars) value for path
                real_value = portfolio_value / cumulative_inflation if portfolio_value > 0 else 0
                sim_path_real.append(real_value)
                year_idx += 1
            
            if portfolio_value <= 0:
                break
        
        all_fi_years.append(fi_year if fi_year is not None else total_years)
        all_fi_ages.append(current_age + (fi_year if fi_year is not None else total_years))
        all_success.append(sim_succeeded)
        all_paths.append(sim_path_real)  # Store real (inflation-adjusted) paths
    
    # Calculate statistics
    fi_years_arr = np.array(all_fi_years)
    fi_ages_arr = np.array(all_fi_ages)
    
    # Percentage of simulations where FI was reached
    fi_reached_count = sum(1 for y in all_fi_years if y < total_years)
    fi_probability = (fi_reached_count / num_simulations) * 100
    
    # Success rate (portfolio lasted through life expectancy)
    success_rate = (sum(all_success) / num_simulations) * 100
    
    # Percentile paths
    max_path_len = max(len(p) for p in all_paths)
    paths_arr = np.array([p + [p[-1]] * (max_path_len - len(p)) for p in all_paths])
    
    # Calculate FI year percentiles (only for simulations that reached FI)
    fi_reached_years = [y for y in all_fi_years if y < total_years]
    if fi_reached_years:
        fi_years_percentiles = {
            "p10": float(np.percentile(fi_reached_years, 10)),
            "p25": float(np.percentile(fi_reached_years, 25)),
            "p50": float(np.percentile(fi_reached_years, 50)),
            "p75": float(np.percentile(fi_reached_years, 75)),
            "p90": float(np.percentile(fi_reached_years, 90)),
        }
    else:
        fi_years_percentiles = {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}
    
    return {
        "fi_probability": float(fi_probability),
        "success_rate": float(success_rate),
        "simulations_run": num_simulations,
        "initial_value": float(initial_value),
        "fi_number": float(fi_number),
        "annual_contributions": float(total_annual_contributions),
        "portfolio_allocation": {
            "stocks": round(avg_stocks_pct * 100, 1),
            "bonds": round(avg_bonds_pct * 100, 1),
            "cash": round(avg_cash_pct * 100, 1),
        },
        "years_to_fi": {
            "median": float(np.percentile(fi_years_arr, 50)),
            "optimistic": float(np.percentile(fi_years_arr, 25)),
            "pessimistic": float(np.percentile(fi_years_arr, 75)),
            "percentiles": fi_years_percentiles,
        },
        "fi_age": {
            "median": int(current_age + np.percentile(fi_years_arr, 50)),
            "optimistic": int(current_age + np.percentile(fi_years_arr, 25)),
            "pessimistic": int(current_age + np.percentile(fi_years_arr, 75)),
        },
        "final_portfolio": {
            "p10": float(np.percentile([p[-1] for p in all_paths], 10)),
            "p25": float(np.percentile([p[-1] for p in all_paths], 25)),
            "p50": float(np.percentile([p[-1] for p in all_paths], 50)),
            "p75": float(np.percentile([p[-1] for p in all_paths], 75)),
            "p90": float(np.percentile([p[-1] for p in all_paths], 90)),
        },
        "projection_paths": {
            "p10": [float(np.percentile(paths_arr[:, y], 10)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
            "p25": [float(np.percentile(paths_arr[:, y], 25)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
            "p50": [float(np.percentile(paths_arr[:, y], 50)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
            "p75": [float(np.percentile(paths_arr[:, y], 75)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
            "p90": [float(np.percentile(paths_arr[:, y], 90)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
        },
        "success_by_retirement_age": calculate_success_by_age(
            all_paths, all_fi_years, current_age, life_expectancy,
            retirement_expenses, withdrawal_rate, social_security_annual, ss_start_age
        )
    }


def calculate_success_by_age(
    all_paths: List[List[float]],
    all_fi_years: List[int],
    current_age: int,
    life_expectancy: int,
    retirement_expenses: float,
    withdrawal_rate: float,
    social_security_annual: float,
    ss_start_age: int
) -> List[dict]:
    """
    Calculate success rates for retiring at different ages.
    
    Returns a list of success rates for each potential retirement age.
    """
    results = []
    num_sims = len(all_paths)
    
    # Check success rates for retirement ages from current_age+5 to life_expectancy-10
    for retire_age in range(current_age + 5, min(life_expectancy - 10, 80), 5):
        year_idx = retire_age - current_age
        
        # Count simulations where portfolio value at this age could support withdrawals
        success_count = 0
        for sim_idx, path in enumerate(all_paths):
            if year_idx < len(path):
                portfolio_at_age = path[year_idx]
                # Simple check: can this portfolio support the withdrawal rate?
                retirement_years = life_expectancy - retire_age
                # Rough success criteria: portfolio > required annual withdrawal * years
                if portfolio_at_age > retirement_expenses * retirement_years * 0.6:
                    success_count += 1
        
        success_rate = (success_count / num_sims) * 100 if num_sims > 0 else 0
        
        results.append({
            "retirement_age": retire_age,
            "years_from_now": retire_age - current_age,
            "success_probability": round(success_rate, 1),
            "recommendation": "Likely" if success_rate >= 80 else "Possible" if success_rate >= 50 else "Risky"
        })
    
    return results


def calculate_years_to_fi(
    current_net_worth: float,
    annual_contributions: float,
    fi_number: float,
    expected_return: float = 0.07,
    inflation_rate: float = 0.03
) -> dict:
    """
    Calculate years until reaching FI number using iterative projection.
    
    DEPRECATED: Use run_monte_carlo_fi_analysis for more accurate results.
    This function is kept for backwards compatibility and quick estimates.
    """
    if current_net_worth >= fi_number:
        return {
            "years_to_fi": 0,
            "fi_achieved": True,
            "final_value": current_net_worth,
            "total_contributions": 0,
            "investment_gains": 0,
            "projection_path": [current_net_worth]
        }
    
    if annual_contributions <= 0 and expected_return <= 0:
        return {
            "years_to_fi": float('inf'),
            "fi_achieved": False,
            "final_value": current_net_worth,
            "total_contributions": 0,
            "investment_gains": 0,
            "projection_path": [current_net_worth],
            "message": "Need positive contributions or returns to reach FI"
        }
    
    # Real return (inflation-adjusted) for calculating years
    real_return = (1 + expected_return) / (1 + inflation_rate) - 1
    
    years = 0
    portfolio = current_net_worth
    path = [portfolio]
    total_contributions = 0
    max_years = 100  # Safety limit
    
    while portfolio < fi_number and years < max_years:
        # Apply return
        portfolio *= (1 + real_return)
        # Add contributions
        portfolio += annual_contributions
        total_contributions += annual_contributions
        years += 1
        path.append(portfolio)
    
    investment_gains = portfolio - current_net_worth - total_contributions
    
    return {
        "years_to_fi": years if years < max_years else float('inf'),
        "fi_achieved": portfolio >= fi_number,
        "fi_age": years,  # Will be added to current age by caller
        "final_value": portfolio,
        "total_contributions": total_contributions,
        "investment_gains": investment_gains,
        "projection_path": path,
        "real_return_used": real_return * 100
    }


def run_fire_monte_carlo(
    accounts_data: List[dict],
    years_accumulation: int,
    years_retirement: int,
    withdrawal_rate: float,
    withdrawal_method: str,
    annual_withdrawal: float,
    num_simulations: int = 1000,
    upper_guardrail: float = 0.05,
    lower_guardrail: float = 0.03,
    guardrail_adjustment: float = 0.10,
    withdrawal_floor: float = 0,
    withdrawal_ceiling: float = 0,
    social_security_annual: float = 0,
    ss_start_year: int = 0,
    pension_annual: float = 0,
    pension_start_year: int = 0
) -> dict:
    """
    Run Monte Carlo simulation for full FIRE journey: accumulation + withdrawal phases.
    
    This simulates:
    1. Accumulation phase: years of saving/investing before retirement
    2. Withdrawal phase: years of drawing down portfolio in retirement
    
    Args:
        accounts_data: List of account data with balances and allocations
        years_accumulation: Years until retirement
        years_retirement: Years in retirement (life_expectancy - retirement_age)
        withdrawal_rate: Safe withdrawal rate as decimal
        withdrawal_method: Withdrawal strategy
        annual_withdrawal: Initial annual withdrawal amount
        num_simulations: Number of simulations to run
        Other params: Strategy-specific parameters
        
    Returns:
        Dictionary with comprehensive simulation results
    """
    # Get historical data
    stock_returns = np.array(HISTORICAL_RETURNS["stocks"])
    bond_returns = np.array(HISTORICAL_RETURNS["bonds"])
    cash_returns = np.array(HISTORICAL_RETURNS["cash"])
    inflation_rates = np.array(HISTORICAL_INFLATION)
    num_historical_years = len(stock_returns)
    
    total_years = years_accumulation + years_retirement
    
    # Results tracking
    all_final_values = []
    all_fi_values = []  # Value at retirement
    all_success = []
    all_years_lasted = []
    all_paths = []
    
    # Initial portfolio value
    initial_value = sum(
        acc["current_balance"] if acc["is_asset"] else -acc["current_balance"]
        for acc in accounts_data
    )
    
    # Annual contributions
    total_annual_contributions = sum(
        acc.get("contribution_monthly", 0) * 12
        for acc in accounts_data if acc.get("is_asset", False)
    )
    
    for sim in range(num_simulations):
        # Initialize account balances
        sim_accounts = {}
        for acc in accounts_data:
            sim_accounts[acc["id"]] = {
                "balance": acc["current_balance"],
                "is_asset": acc["is_asset"],
                "contribution_monthly": acc.get("contribution_monthly", 0),
                "stocks_pct": acc.get("stocks_pct", 80) / 100,
                "bonds_pct": acc.get("bonds_pct", 15) / 100,
                "cash_pct": acc.get("cash_pct", 5) / 100,
                "interest_rate": acc.get("interest_rate", 0) / 100 / 12,
            }
        
        portfolio_value = initial_value
        sim_path = [portfolio_value]
        cumulative_inflation = 1.0
        sim_succeeded = True
        years_lasted = total_years
        fi_value = 0
        
        # Use block bootstrap for sequential years
        block_size = min(total_years, 10)
        year_idx = 0
        
        while year_idx < total_years:
            max_start = num_historical_years - block_size
            block_start = random.randint(0, max(0, max_start))
            
            for block_year in range(block_size):
                if year_idx >= total_years:
                    break
                
                hist_idx = (block_start + block_year) % num_historical_years
                yr_stock = stock_returns[hist_idx]
                yr_bond = bond_returns[hist_idx]
                yr_cash = cash_returns[hist_idx]
                
                inf_idx = min(hist_idx, len(inflation_rates) - 1)
                yr_inflation = inflation_rates[inf_idx]
                cumulative_inflation *= (1 + yr_inflation)
                
                # Phase determination
                is_accumulation = year_idx < years_accumulation
                
                # Update all accounts
                for acc_id, acc in sim_accounts.items():
                    if acc["is_asset"]:
                        # Apply portfolio return
                        portfolio_return = (
                            acc["stocks_pct"] * yr_stock +
                            acc["bonds_pct"] * yr_bond +
                            acc["cash_pct"] * yr_cash
                        )
                        acc["balance"] *= (1 + portfolio_return)
                        
                        # Only add contributions during accumulation
                        if is_accumulation:
                            acc["balance"] += acc["contribution_monthly"] * 12
                    else:
                        # Liability
                        for month in range(12):
                            acc["balance"] *= (1 + acc["interest_rate"])
                            acc["balance"] = max(0, acc["balance"] - acc["contribution_monthly"])
                
                # Calculate net worth
                portfolio_value = sum(
                    acc["balance"] if acc["is_asset"] else -acc["balance"]
                    for acc in sim_accounts.values()
                )
                
                # Record FI value (at end of accumulation)
                if year_idx == years_accumulation - 1:
                    fi_value = portfolio_value
                
                # Apply withdrawals during retirement
                if not is_accumulation and portfolio_value > 0:
                    # Calculate other income for this year
                    retirement_year = year_idx - years_accumulation
                    other_income = 0
                    if ss_start_year > 0 and retirement_year >= ss_start_year:
                        other_income += social_security_annual * cumulative_inflation
                    if pension_start_year > 0 and retirement_year >= pension_start_year:
                        other_income += pension_annual * cumulative_inflation
                    
                    # Calculate withdrawal based on method
                    year_withdrawal = 0
                    
                    if withdrawal_method == "fixed_swr":
                        year_withdrawal = annual_withdrawal * cumulative_inflation - other_income
                        
                    elif withdrawal_method == "variable_pct":
                        remaining_years = max(1, years_retirement - retirement_year)
                        vpw_rate = 1 / remaining_years
                        year_withdrawal = portfolio_value * vpw_rate - other_income
                        
                    elif withdrawal_method == "guardrails":
                        base_withdrawal = annual_withdrawal * cumulative_inflation
                        current_rate = base_withdrawal / portfolio_value if portfolio_value > 0 else 0
                        
                        if current_rate > upper_guardrail:
                            year_withdrawal = base_withdrawal * (1 - guardrail_adjustment)
                        elif current_rate < lower_guardrail:
                            year_withdrawal = base_withdrawal * (1 + guardrail_adjustment)
                        else:
                            year_withdrawal = base_withdrawal
                        year_withdrawal -= other_income
                        
                    elif withdrawal_method == "floor_ceiling":
                        base_withdrawal = portfolio_value * withdrawal_rate
                        adj_floor = withdrawal_floor * cumulative_inflation
                        adj_ceiling = withdrawal_ceiling * cumulative_inflation
                        year_withdrawal = max(adj_floor, min(base_withdrawal, adj_ceiling)) - other_income
                    
                    year_withdrawal = max(0, year_withdrawal)  # Can't withdraw negative
                    
                    # Distribute withdrawal across accounts proportionally
                    total_assets = sum(acc["balance"] for acc in sim_accounts.values() if acc["is_asset"])
                    if total_assets > 0 and year_withdrawal > 0:
                        for acc_id, acc in sim_accounts.items():
                            if acc["is_asset"]:
                                acc_share = acc["balance"] / total_assets
                                withdrawal_from_acc = min(acc["balance"], year_withdrawal * acc_share)
                                acc["balance"] -= withdrawal_from_acc
                    
                    # Recalculate after withdrawal
                    portfolio_value = sum(
                        acc["balance"] if acc["is_asset"] else -acc["balance"]
                        for acc in sim_accounts.values()
                    )
                
                # Check for portfolio depletion
                if portfolio_value <= 0:
                    sim_succeeded = False
                    years_lasted = year_idx
                    portfolio_value = 0
                    break
                
                sim_path.append(portfolio_value)
                year_idx += 1
            
            if portfolio_value <= 0:
                break
        
        all_final_values.append(portfolio_value)
        all_fi_values.append(fi_value)
        all_success.append(sim_succeeded)
        all_years_lasted.append(years_lasted)
        all_paths.append(sim_path)
    
    # Calculate statistics
    final_values_arr = np.array(all_final_values)
    fi_values_arr = np.array(all_fi_values)
    years_lasted_arr = np.array(all_years_lasted)
    
    success_count = sum(all_success)
    success_rate = (success_count / num_simulations) * 100
    
    # Percentile paths for visualization
    paths_arr = np.array([p + [p[-1]] * (total_years + 1 - len(p)) for p in all_paths])
    
    return {
        "success_rate": float(success_rate),
        "success_count": int(success_count),
        "failure_count": int(num_simulations - success_count),
        "initial_value": float(initial_value),
        "annual_contributions": float(total_annual_contributions),
        "years_accumulation": years_accumulation,
        "years_retirement": years_retirement,
        "total_years": total_years,
        "fi_value_percentiles": {
            "p10": float(np.percentile(fi_values_arr, 10)),
            "p25": float(np.percentile(fi_values_arr, 25)),
            "p50": float(np.percentile(fi_values_arr, 50)),
            "p75": float(np.percentile(fi_values_arr, 75)),
            "p90": float(np.percentile(fi_values_arr, 90)),
        },
        "final_value_percentiles": {
            "p10": float(np.percentile(final_values_arr, 10)),
            "p25": float(np.percentile(final_values_arr, 25)),
            "p50": float(np.percentile(final_values_arr, 50)),
            "p75": float(np.percentile(final_values_arr, 75)),
            "p90": float(np.percentile(final_values_arr, 90)),
            "mean": float(np.mean(final_values_arr)),
        },
        "years_lasted_percentiles": {
            "p10": float(np.percentile(years_lasted_arr, 10)),
            "p25": float(np.percentile(years_lasted_arr, 25)),
            "p50": float(np.percentile(years_lasted_arr, 50)),
            "min": float(np.min(years_lasted_arr)),
        },
        "paths": {
            "p10": [float(np.percentile(paths_arr[:, y], 10)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
            "p25": [float(np.percentile(paths_arr[:, y], 25)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
            "p50": [float(np.percentile(paths_arr[:, y], 50)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
            "p75": [float(np.percentile(paths_arr[:, y], 75)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
            "p90": [float(np.percentile(paths_arr[:, y], 90)) for y in range(min(total_years + 1, paths_arr.shape[1]))],
        }
    }


@router.post("/tools/fire/calculate")
async def calculate_fire_plan(
    request: Request,
    body: FIRERequest,
    db: Session = Depends(get_db)
):
    """
    Calculate comprehensive FIRE (Financial Independence, Retire Early) plan.
    
    This endpoint:
    1. Retrieves current net worth and account data from the user's portfolio
    2. Calculates the FI number based on FIRE type and withdrawal strategy
    3. Projects years to FI using actual contribution rates and portfolio allocations
    4. Runs Monte Carlo simulations for both accumulation and withdrawal phases
    5. Compares different FIRE approaches
    
    Returns detailed metrics including:
    - FI Number and progress
    - Years to FI with projection path
    - Monte Carlo success rates
    - FIRE type comparisons
    - Withdrawal strategy details
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Get user's accounts
    accounts = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_active == True
    ).all()
    
    # Build accounts data with latest balances and contribution settings
    accounts_data = []
    total_assets = 0
    total_liabilities = 0
    total_monthly_contributions = 0
    
    # Calculate weighted average expected return
    weighted_return_sum = 0
    total_asset_value = 0
    
    for acc in accounts:
        # Get latest balance
        latest_bal = db.query(AccountBalance).filter(
            AccountBalance.account_id == acc.id
        ).order_by(AccountBalance.balance_date.desc()).first()
        
        current_balance = latest_bal.balance if latest_bal else 0
        
        # Get contribution settings
        contrib = db.query(AccountContribution).filter(
            AccountContribution.account_id == acc.id
        ).first()
        
        # Calculate monthly contribution
        contrib_amount = 0
        expected_return = 7.0
        stocks_pct = 80
        bonds_pct = 15
        cash_pct = 5
        interest_rate = 0
        
        if contrib:
            raw_amount = contrib.amount if contrib.amount is not None else 0
            freq = contrib.frequency or "monthly"
            
            # Convert to monthly
            freq_multiplier = {
                "annually": 1/12, "quarterly": 1/3, "monthly": 1,
                "semi-monthly": 2, "bi-weekly": 2.17, "weekly": 4.33
            }.get(freq, 1)
            
            contrib_amount = raw_amount * freq_multiplier
            
            if contrib.expected_return is not None:
                expected_return = contrib.expected_return
            if contrib.stocks_pct is not None:
                stocks_pct = contrib.stocks_pct
            if contrib.bonds_pct is not None:
                bonds_pct = contrib.bonds_pct
            if contrib.cash_pct is not None:
                cash_pct = contrib.cash_pct
            if contrib.interest_rate is not None:
                interest_rate = contrib.interest_rate
        
        if acc.is_asset:
            total_assets += current_balance
            total_monthly_contributions += contrib_amount
            weighted_return_sum += current_balance * expected_return / 100
            total_asset_value += current_balance
        else:
            total_liabilities += current_balance
        
        accounts_data.append({
            "id": acc.id,
            "name": acc.name,
            "account_type": acc.account_type,
            "is_asset": acc.is_asset,
            "current_balance": current_balance,
            "contribution_monthly": contrib_amount,
            "expected_return": expected_return,
            "stocks_pct": stocks_pct,
            "bonds_pct": bonds_pct,
            "cash_pct": cash_pct,
            "interest_rate": interest_rate
        })
    
    current_net_worth = total_assets - total_liabilities
    annual_contributions = total_monthly_contributions * 12
    
    # Convert inputs
    inflation_rate = body.inflation_rate / 100
    withdrawal_rate = body.withdrawal_rate / 100
    
    # Social Security and pension (annual amounts)
    social_security_annual = body.social_security_monthly * 12
    pension_annual = body.pension_monthly * 12
    
    # Calculate FI Number based on withdrawal strategy
    fi_result = calculate_fi_number(
        retirement_expenses=body.retirement_expenses,
        withdrawal_rate=withdrawal_rate,
        fire_type=body.fire_type,
        current_age=body.current_age,
        life_expectancy=body.life_expectancy,
        target_retirement_age=body.target_retirement_age,
        inflation_rate=inflation_rate,
        social_security_annual=social_security_annual,
        pension_annual=pension_annual
    )
    
    fi_number = fi_result["adjusted_fi_number"]
    
    # Calculate progress
    progress_pct = min((total_assets / fi_number) * 100, 100) if fi_number > 0 else 0
    
    # =========================================================================
    # Run Monte Carlo analysis for FIRE projections
    # Uses actual portfolio allocations and historical returns
    # =========================================================================
    mc_fi_analysis = None
    if len(accounts_data) > 0:
        mc_fi_analysis = run_monte_carlo_fi_analysis(
            accounts_data=accounts_data,
            fi_number=fi_number,
            retirement_expenses=body.retirement_expenses,
            current_age=body.current_age,
            life_expectancy=body.life_expectancy,
            withdrawal_rate=withdrawal_rate,
            withdrawal_method=body.withdrawal_method,
            num_simulations=body.num_simulations,
            social_security_annual=social_security_annual,
            ss_start_age=body.social_security_start_age,
            pension_annual=pension_annual,
            pension_start_age=body.pension_start_age,
            upper_guardrail=body.upper_guardrail / 100,
            lower_guardrail=body.lower_guardrail / 100,
            guardrail_adjustment=body.guardrail_adjustment / 100,
            withdrawal_floor=body.withdrawal_floor,
            withdrawal_ceiling=body.withdrawal_ceiling
        )
    
    # Extract years to FI from Monte Carlo results
    if mc_fi_analysis:
        years_to_fi_median = mc_fi_analysis["years_to_fi"]["median"]
        years_to_fi_optimistic = mc_fi_analysis["years_to_fi"]["optimistic"]
        years_to_fi_pessimistic = mc_fi_analysis["years_to_fi"]["pessimistic"]
        fi_age_median = mc_fi_analysis["fi_age"]["median"]
        fi_age_optimistic = mc_fi_analysis["fi_age"]["optimistic"]
        fi_age_pessimistic = mc_fi_analysis["fi_age"]["pessimistic"]
        fi_probability = mc_fi_analysis["fi_probability"]
        success_rate = mc_fi_analysis["success_rate"]
    else:
        # Fallback to simple calculation if no accounts
        years_to_fi_median = None
        years_to_fi_optimistic = None
        years_to_fi_pessimistic = None
        fi_age_median = None
        fi_age_optimistic = None
        fi_age_pessimistic = None
        fi_probability = 0
        success_rate = 0
    
    # FIRE types comparison (run simplified MC for each type)
    fire_types_comparison = []
    swr = withdrawal_rate if withdrawal_rate > 0 else 0.04
    
    fire_types = [
        {"type": "lean", "name": "Lean FIRE", "icon": "🥗", "expense_mult": 0.6},
        {"type": "regular", "name": "Regular FIRE", "icon": "🏠", "expense_mult": 1.0},
        {"type": "fat", "name": "Fat FIRE", "icon": "🎉", "expense_mult": 1.5},
        {"type": "coast", "name": "Coast FIRE", "icon": "⛵", "expense_mult": 0.7},
        {"type": "barista", "name": "Barista FIRE", "icon": "☕", "expense_mult": 0.7},
    ]
    
    for ft in fire_types:
        expenses = body.retirement_expenses * ft["expense_mult"]
        type_fi = calculate_fi_number(
            retirement_expenses=expenses,
            withdrawal_rate=swr,
            fire_type=ft["type"],
            current_age=body.current_age,
            life_expectancy=body.life_expectancy,
            target_retirement_age=body.target_retirement_age,
            inflation_rate=inflation_rate,
            social_security_annual=social_security_annual,
            pension_annual=pension_annual
        )
        
        # Run quick Monte Carlo for this FIRE type (fewer simulations for speed)
        type_mc = None
        if len(accounts_data) > 0:
            type_mc = run_monte_carlo_fi_analysis(
                accounts_data=accounts_data,
                fi_number=type_fi["adjusted_fi_number"],
                retirement_expenses=expenses,
                current_age=body.current_age,
                life_expectancy=body.life_expectancy,
                withdrawal_rate=swr,
                withdrawal_method=body.withdrawal_method,
                num_simulations=200,  # Fewer simulations for comparison
                social_security_annual=social_security_annual,
                ss_start_age=body.social_security_start_age,
                pension_annual=pension_annual,
                pension_start_age=body.pension_start_age
            )
        
        fire_types_comparison.append({
            "type": ft["type"],
            "name": ft["name"],
            "icon": ft["icon"],
            "annual_spending": expenses,
            "fi_number": type_fi["adjusted_fi_number"],
            "monthly_withdrawal": expenses / 12,
            "years_to_fi": type_mc["years_to_fi"]["median"] if type_mc else None,
            "fi_age": type_mc["fi_age"]["median"] if type_mc else None,
            "success_rate": type_mc["success_rate"] if type_mc else 0,
            "fi_probability": type_mc["fi_probability"] if type_mc else 0
        })
    
    # Build response
    response = {
        "success": True,
        "profile": {
            "current_age": body.current_age,
            "target_retirement_age": body.target_retirement_age,
            "life_expectancy": body.life_expectancy,
            "retirement_years": body.life_expectancy - body.target_retirement_age
        },
        "current_status": {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "net_worth": current_net_worth,
            "annual_contributions": annual_contributions,
            "monthly_contributions": total_monthly_contributions,
            "portfolio_allocation": mc_fi_analysis["portfolio_allocation"] if mc_fi_analysis else {"stocks": 80, "bonds": 15, "cash": 5},
            "num_accounts": len(accounts_data)
        },
        "fi_calculation": {
            "fi_number": fi_number,
            "base_fi_number": fi_result["base_fi_number"],
            "fire_type": body.fire_type,
            "withdrawal_rate": withdrawal_rate * 100,
            "expenses_from_portfolio": fi_result["expenses_from_portfolio"],
            "other_income_annual": fi_result["other_income_annual"],
            "description": fi_result.get("description", "")
        },
        "progress": {
            "current_value": total_assets,
            "fi_number": fi_number,
            "progress_percentage": progress_pct,
            "remaining_amount": max(0, fi_number - total_assets)
        },
        "time_to_fi": {
            "method": "monte_carlo",
            "simulations_run": mc_fi_analysis["simulations_run"] if mc_fi_analysis else 0,
            "years_to_fi": {
                "median": years_to_fi_median,
                "optimistic": years_to_fi_optimistic,  # 25th percentile (faster)
                "pessimistic": years_to_fi_pessimistic,  # 75th percentile (slower)
            },
            "fi_age": {
                "median": fi_age_median,
                "optimistic": fi_age_optimistic,
                "pessimistic": fi_age_pessimistic,
            },
            "fi_probability": fi_probability,  # % of simulations that reached FI
            "success_rate": success_rate,  # % where portfolio lasted through life expectancy
            "projection_paths": mc_fi_analysis["projection_paths"] if mc_fi_analysis else None,
            "success_by_retirement_age": mc_fi_analysis["success_by_retirement_age"] if mc_fi_analysis else []
        },
        "withdrawal_strategy": {
            "method": body.withdrawal_method,
            "annual_withdrawal": body.retirement_expenses,
            "monthly_withdrawal": body.retirement_expenses / 12,
            "social_security_annual": social_security_annual,
            "pension_annual": pension_annual
        },
        "fire_types_comparison": fire_types_comparison,
        "monte_carlo": {
            "final_portfolio": mc_fi_analysis["final_portfolio"] if mc_fi_analysis else None,
            "success_rate": success_rate,
            "fi_probability": fi_probability,
        }
    }
    
    logger.info(f"FIRE MC analysis for user {user.username}: FI Number=${fi_number:,.0f}, "
                f"Median Years to FI={years_to_fi_median}, Success Rate={success_rate:.1f}%")
    
    return JSONResponse(response)


@router.get("/tools/fire/summary")
async def get_fire_summary(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get a quick FIRE summary based on current net worth and default assumptions.
    
    This is a lightweight endpoint for displaying basic FIRE metrics on the dashboard
    without requiring all the input parameters of a full calculation.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Get total assets and contributions
    accounts = db.query(Account).filter(
        Account.user_id == user.id,
        Account.is_active == True,
        Account.is_asset == True
    ).all()
    
    total_assets = 0
    total_monthly_contributions = 0
    
    for acc in accounts:
        latest_bal = db.query(AccountBalance).filter(
            AccountBalance.account_id == acc.id
        ).order_by(AccountBalance.balance_date.desc()).first()
        
        if latest_bal:
            total_assets += latest_bal.balance
        
        contrib = db.query(AccountContribution).filter(
            AccountContribution.account_id == acc.id
        ).first()
        
        if contrib and contrib.amount:
            freq_multiplier = {"annually": 1/12, "quarterly": 1/3, "monthly": 1}.get(
                contrib.frequency or "monthly", 1
            )
            total_monthly_contributions += contrib.amount * freq_multiplier
    
    # Default assumptions
    default_retirement_expenses = 50000  # $50k/year
    default_swr = 0.04  # 4%
    
    fi_number = default_retirement_expenses / default_swr
    progress_pct = min((total_assets / fi_number) * 100, 100) if fi_number > 0 else 0
    
    return JSONResponse({
        "total_assets": total_assets,
        "annual_contributions": total_monthly_contributions * 12,
        "fi_number_default": fi_number,
        "progress_percentage": progress_pct,
        "has_accounts": len(accounts) > 0
    })


# =============================================================================
# About Page
# =============================================================================

@router.get("/about")
def about_page(request: Request, db: Session = Depends(get_db)):
    """About page with application documentation."""
    user = get_current_user(request, db)
    
    logger.info("About page accessed")
    
    profile_picture_b64 = None
    profile_picture_type = None
    dark_mode = False
    
    if user:
        profile_picture_b64, profile_picture_type = get_profile_picture_data(user)
        dark_mode = user.dark_mode
    
    return templates.TemplateResponse("about.html", {
        "request": request,
        "title": "About",
        "user": user,
        "dark_mode": dark_mode,
        "profile_picture_b64": profile_picture_b64,
        "profile_picture_type": profile_picture_type
    })
