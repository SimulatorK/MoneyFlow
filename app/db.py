from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models import Base
from app.models.user import User
from app.models.income_taxes import IncomeTaxes
from app.models.expense import Category, SubCategory, Expense
from app.models.budget import BudgetCategory, FixedCost, BudgetItem
from app.models.mortgage import MortgageScenario
from app.models.networth import Account, AccountBalance, AccountContribution, MonteCarloScenario

SQLALCHEMY_DATABASE_URL = "sqlite:///./masterbudget.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    Create tables if they don't exist.
    For schema changes, use Alembic migrations instead:
        poetry run alembic revision --autogenerate -m "Description of change"
        poetry run alembic upgrade head
    """
    Base.metadata.create_all(bind=engine)


# Only create tables on first run if database doesn't exist
# For schema changes, use: poetry run alembic upgrade head
init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
