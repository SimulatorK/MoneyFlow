from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
import base64

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Curated list of reputable financial resources
FINANCIAL_RESOURCES = [
    {
        "category": "Personal Finance Blogs",
        "sources": [
            {
                "name": "NerdWallet",
                "url": "https://www.nerdwallet.com/blog/",
                "description": "Comprehensive personal finance guidance, credit card reviews, and money management tips",
                "icon": "💳"
            },
            {
                "name": "The Motley Fool",
                "url": "https://www.fool.com/",
                "description": "Investment advice, stock analysis, and retirement planning strategies",
                "icon": "📈"
            },
            {
                "name": "Investopedia",
                "url": "https://www.investopedia.com/",
                "description": "Financial education, investing tutorials, and market analysis",
                "icon": "📚"
            },
            {
                "name": "Mr. Money Mustache",
                "url": "https://www.mrmoneymustache.com/",
                "description": "Early retirement strategies and frugal living philosophy",
                "icon": "🧔"
            },
        ]
    },
    {
        "category": "Tax Resources",
        "sources": [
            {
                "name": "IRS.gov",
                "url": "https://www.irs.gov/",
                "description": "Official IRS tax information, forms, and filing resources",
                "icon": "🏛️"
            },
            {
                "name": "Tax Foundation",
                "url": "https://taxfoundation.org/",
                "description": "Tax policy research, analysis, and state tax guides",
                "icon": "📊"
            },
            {
                "name": "Kiplinger Tax",
                "url": "https://www.kiplinger.com/taxes",
                "description": "Tax tips, deduction guides, and tax planning strategies",
                "icon": "💰"
            },
        ]
    },
    {
        "category": "Budgeting & Saving",
        "sources": [
            {
                "name": "YNAB Blog",
                "url": "https://www.ynab.com/blog/",
                "description": "Zero-based budgeting strategies and financial wellness",
                "icon": "📋"
            },
            {
                "name": "The Balance",
                "url": "https://www.thebalancemoney.com/",
                "description": "Practical budgeting advice and money management guides",
                "icon": "⚖️"
            },
            {
                "name": "Bankrate",
                "url": "https://www.bankrate.com/",
                "description": "Savings rates, financial calculators, and banking advice",
                "icon": "🏦"
            },
        ]
    },
    {
        "category": "Investment & Retirement",
        "sources": [
            {
                "name": "Bogleheads",
                "url": "https://www.bogleheads.org/",
                "description": "Index fund investing philosophy and community wisdom",
                "icon": "📉"
            },
            {
                "name": "Fidelity Learning Center",
                "url": "https://www.fidelity.com/learning-center/overview",
                "description": "Investment education and retirement planning tools",
                "icon": "🎓"
            },
            {
                "name": "Vanguard Insights",
                "url": "https://investor.vanguard.com/investor-resources-education",
                "description": "Long-term investing principles and market perspectives",
                "icon": "🚢"
            },
        ]
    },
    {
        "category": "Financial News",
        "sources": [
            {
                "name": "Bloomberg",
                "url": "https://www.bloomberg.com/",
                "description": "Global financial news, market data, and analysis",
                "icon": "📰"
            },
            {
                "name": "CNBC",
                "url": "https://www.cnbc.com/personal-finance/",
                "description": "Personal finance news and market updates",
                "icon": "📺"
            },
            {
                "name": "MarketWatch",
                "url": "https://www.marketwatch.com/",
                "description": "Stock market news and financial analysis",
                "icon": "👁️"
            },
        ]
    },
    {
        "category": "Tools & Calculators",
        "sources": [
            {
                "name": "SmartAsset Calculators",
                "url": "https://smartasset.com/taxes",
                "description": "Tax calculators, paycheck estimators, and financial planning tools",
                "icon": "🧮"
            },
            {
                "name": "CalcXML",
                "url": "https://www.calcxml.com/",
                "description": "Comprehensive financial calculators for all life stages",
                "icon": "➗"
            },
            {
                "name": "Salary.com",
                "url": "https://www.salary.com/",
                "description": "Salary data, compensation benchmarks, and career tools",
                "icon": "💼"
            },
        ]
    },
]


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


@router.get("/forum")
def forum_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    profile_picture_b64, profile_picture_type = get_profile_picture_data(user)
    
    return templates.TemplateResponse("forum.html", {
        "request": request,
        "title": "Financial Resources",
        "user": user,
        "profile_picture_b64": profile_picture_b64,
        "profile_picture_type": profile_picture_type,
        "dark_mode": user.dark_mode,
        "resources": FINANCIAL_RESOURCES
    })

