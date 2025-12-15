"""
MoneyFlow - Personal Finance Management Application

Main FastAPI application entry point. Configures routes, middleware,
and application lifecycle events.

Version: 1.0.0
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
# Import logging configuration (initializes logging)
from app.logging_config import get_logger
from fastapi.responses import FileResponse

# Import route modules
from app.routes import auth, home
from app.routes import income_taxes
from app.routes import expenses
from app.routes import budget
from app.routes import profile
from app.routes import forum
from app.routes import tools
from app.routes import tutorial

# Get logger for this module
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    
    Handles startup and shutdown events for the application.
    """
    # Startup
    logger.info("=" * 60)
    logger.info("MoneyFlow Application Starting")
    logger.info(f"Version: {app.version}")
    logger.info("=" * 60)
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("MoneyFlow Application Shutting Down")
    logger.info("=" * 60)


# Create FastAPI application instance
app = FastAPI(
    title="MoneyFlow",
    description="Personal finance management application for tracking income, expenses, budgets, and taxes.",
    version="1.2.0",  # v1.2.0 - Monte Carlo simulations, portfolio allocation, CSV bulk upload
    lifespan=lifespan
)

@app.get("/")
async def root():
    return RedirectResponse(url="/home")

# # Add apple touch icon
# apple_touch_icon_path = "static/apple-touch-icon.png"

# @app.get("/apple-touch-icon.png", include_in_schema=False)
# async def get_apple_touch_icon():
#     return FileResponse(apple_touch_icon_path)

# Mount static files directory
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Configure Jinja2 templates
templates = Jinja2Templates(directory="app/templates")

# Include route modules
app.include_router(auth.router, tags=["Authentication"])
app.include_router(tutorial.router, tags=["Tutorial"])
app.include_router(home.router, tags=["Dashboard"])
app.include_router(income_taxes.router, tags=["Income & Taxes"])
app.include_router(expenses.router, tags=["Expenses"])
app.include_router(budget.router, tags=["Budget"])
app.include_router(profile.router, tags=["Profile"])
app.include_router(tools.router, tags=["Tools"])
app.include_router(forum.router, tags=["Resources"])

logger.info("All routes registered successfully")
