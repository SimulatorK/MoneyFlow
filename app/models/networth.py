"""
Net Worth Models

This module defines database models for tracking net worth including:
- Accounts (assets and liabilities)
- Balance history over time
- Contribution settings for projections
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, DateTime, Date
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db import Base


class Account(Base):
    """
    Model for financial accounts (assets or liabilities).
    
    Account types include:
    - Assets: 401k, IRA, Roth IRA, HSA, Brokerage, Savings, Checking, etc.
    - Liabilities: Mortgage, Car Loan, Student Loan, Credit Card, etc.
    
    Attributes:
        id: Primary key
        user_id: Foreign key to user
        name: User-defined account name
        account_type: Type of account (401k, ira, roth_ira, hsa, brokerage, savings, checking, mortgage, car_loan, etc.)
        is_asset: True for assets, False for liabilities
        institution: Optional institution name (bank, brokerage)
        notes: Optional notes about the account
        created_at: When the account was created
        is_active: Whether the account is active
    """
    __tablename__ = "networth_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    account_type = Column(String(50), nullable=False)  # 401k, ira, roth_ira, hsa, brokerage, savings, checking, mortgage, car_loan, student_loan, credit_card, other
    is_asset = Column(Boolean, default=True, nullable=False)
    institution = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", backref="networth_accounts")
    balances = relationship("AccountBalance", back_populates="account", cascade="all, delete-orphan")
    contribution = relationship("AccountContribution", back_populates="account", uselist=False, cascade="all, delete-orphan")


class AccountBalance(Base):
    """
    Model for tracking account balance at a point in time.
    
    Allows users to add balance data points over time to track progress.
    
    Attributes:
        id: Primary key
        account_id: Foreign key to account
        balance_date: Date of the balance
        balance: Account balance on this date
        notes: Optional notes about this balance entry
        created_at: When the entry was created
    """
    __tablename__ = "networth_balances"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("networth_accounts.id"), nullable=False)
    balance_date = Column(Date, nullable=False)
    balance = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    account = relationship("Account", back_populates="balances")


class AccountContribution(Base):
    """
    Model for tracking planned contributions to an account.
    
    Used for projection planning.
    
    Attributes:
        id: Primary key
        account_id: Foreign key to account
        amount: Contribution amount
        frequency: How often the contribution is made (weekly, bi-weekly, monthly, quarterly, annually)
        employer_match: Optional employer match amount (for 401k etc.)
        employer_match_limit: Maximum employer match percentage
        expected_return: Expected annual return rate for projections (e.g., 7.0 for 7%)
        interest_rate: Interest rate for liabilities (e.g., 6.5 for 6.5% APR)
        stocks_pct: Percentage of portfolio in stocks (0-100)
        bonds_pct: Percentage of portfolio in bonds (0-100)
        cash_pct: Percentage of portfolio in cash (0-100)
        notes: Optional notes
    """
    __tablename__ = "networth_contributions"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("networth_accounts.id"), nullable=False, unique=True)
    amount = Column(Float, default=0)
    frequency = Column(String(20), default="monthly")  # weekly, bi-weekly, monthly, quarterly, annually
    employer_match = Column(Float, default=0)  # Fixed amount or percentage
    employer_match_type = Column(String(10), default="percent")  # percent or fixed
    employer_match_limit = Column(Float, default=0)  # Max match percentage of salary
    expected_return = Column(Float, default=7.0)  # Expected annual return for assets (%)
    interest_rate = Column(Float, default=0)  # Interest rate for liabilities (APR %)
    # Portfolio allocation (must sum to 100)
    stocks_pct = Column(Float, default=80.0)  # % in stocks
    bonds_pct = Column(Float, default=15.0)  # % in bonds
    cash_pct = Column(Float, default=5.0)  # % in cash
    notes = Column(Text, nullable=True)
    
    # Relationship
    account = relationship("Account", back_populates="contribution")


# Account type choices for UI
ACCOUNT_TYPES = {
    "assets": [
        ("401k", "401(k) Traditional"),
        ("roth_401k", "401(k) Roth"),
        ("after_tax_401k", "401(k) After-Tax"),
        ("403b", "403(b)"),
        ("457", "457 Plan"),
        ("ira", "Traditional IRA"),
        ("roth_ira", "Roth IRA"),
        ("sep_ira", "SEP IRA"),
        ("simple_ira", "SIMPLE IRA"),
        ("hsa", "HSA"),
        ("brokerage", "Brokerage Account"),
        ("savings", "Savings Account"),
        ("checking", "Checking Account"),
        ("cd", "Certificate of Deposit"),
        ("money_market", "Money Market"),
        ("real_estate", "Real Estate"),
        ("crypto", "Cryptocurrency"),
        ("other_asset", "Other Asset"),
    ],
    "liabilities": [
        ("mortgage", "Mortgage"),
        ("home_equity", "Home Equity Loan/HELOC"),
        ("car_loan", "Auto Loan"),
        ("student_loan", "Student Loan"),
        ("personal_loan", "Personal Loan"),
        ("credit_card", "Credit Card"),
        ("medical_debt", "Medical Debt"),
        ("other_liability", "Other Liability"),
    ]
}

# Tax treatment categories for investment analysis
# tax_free: Qualified withdrawals are tax-free (Roth accounts, HSA for medical)
# tax_deferred: Withdrawals taxed as ordinary income (Traditional 401k, IRA)
# taxable: Subject to capital gains (Brokerage accounts)
# partially_taxable: Mixed treatment (After-tax 401k - basis tax-free, gains taxed)
TAX_TREATMENT = {
    "401k": "tax_deferred",
    "roth_401k": "tax_free",
    "after_tax_401k": "partially_taxable",
    "403b": "tax_deferred",
    "457": "tax_deferred",
    "ira": "tax_deferred",
    "roth_ira": "tax_free",
    "sep_ira": "tax_deferred",
    "simple_ira": "tax_deferred",
    "hsa": "tax_free",  # Tax-free for qualified medical expenses
    "brokerage": "taxable",
    "savings": "taxable",
    "checking": "taxable",
    "cd": "taxable",
    "money_market": "taxable",
    "real_estate": "taxable",
    "crypto": "taxable",
    "other_asset": "taxable",
}

FREQUENCY_CHOICES = [
    ("weekly", "Weekly"),
    ("bi-weekly", "Bi-Weekly"),
    ("semi-monthly", "Semi-Monthly"),
    ("monthly", "Monthly"),
    ("quarterly", "Quarterly"),
    ("annually", "Annually"),
]


class MonteCarloScenario(Base):
    """
    Model for saving Monte Carlo simulation scenarios.
    
    Stores the configuration and results of a Monte Carlo simulation
    for investment projections.
    
    Attributes:
        id: Primary key
        user_id: Foreign key to user
        name: User-defined scenario name
        projection_years: Number of years to project
        num_simulations: Number of Monte Carlo simulations run
        settings_json: JSON string of account settings used
        results_json: JSON string of simulation results
        created_at: When the scenario was created
    """
    __tablename__ = "monte_carlo_scenarios"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    projection_years = Column(Integer, default=30)
    num_simulations = Column(Integer, default=1000)
    settings_json = Column(Text, nullable=True)  # Account configs snapshot
    results_json = Column(Text, nullable=True)  # Simulation results
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", backref="monte_carlo_scenarios")


# Historical annual returns for Monte Carlo simulations (1928-2023 data)
# Sources: NYU Stern, Damodaran historical data
HISTORICAL_RETURNS = {
    "stocks": [
        # Returns for S&P 500 equivalent (partial list for simulation)
        0.4381, -0.0824, -0.2512, -0.4384, -0.0864, 0.4998, -0.0119, 0.4674,
        0.3194, -0.3534, 0.2928, -0.0110, -0.1078, -0.1243, 0.1943, 0.2556,
        0.1906, 0.3640, -0.0806, 0.0548, 0.0565, 0.1831, 0.3023, 0.2368,
        0.1828, -0.0099, 0.2640, 0.2289, -0.0843, 0.1661, 0.1244, -0.1006,
        0.2379, 0.1100, -0.0873, 0.2383, 0.1606, 0.1256, -0.0994, 0.1836,
        0.3242, -0.0491, 0.2155, 0.2256, 0.0627, 0.3173, 0.1867, 0.0525,
        0.1618, 0.3124, -0.0306, 0.3049, 0.0762, 0.1008, 0.0132, 0.3758,
        0.2296, 0.3336, 0.2858, 0.2104, -0.0910, -0.1189, -0.2210, 0.2868,
        0.1088, 0.0491, 0.1579, 0.0549, -0.3700, 0.2646, 0.1506, 0.0211,
        0.1600, 0.3239, 0.1369, 0.0138, 0.1196, 0.2183, -0.0438, 0.3149,
        0.1840, 0.2861, -0.1811, 0.2688, -0.1932, 0.2659  # Through 2023
    ],
    "bonds": [
        # 10-Year Treasury Bond returns
        0.0084, 0.0342, 0.0468, 0.0516, 0.0022, 0.0444, 0.0541, 0.0467,
        0.0012, 0.0502, 0.0025, 0.0267, 0.0601, 0.0238, 0.0280, 0.0225,
        0.0165, 0.0021, 0.0313, 0.0606, 0.0056, 0.0084, 0.0229, 0.0362,
        0.0096, 0.0239, 0.0356, 0.0690, 0.0043, 0.0115, 0.0197, 0.0019,
        0.0169, 0.0382, 0.0032, 0.0370, 0.0129, 0.0156, -0.0011, 0.0386,
        0.1470, 0.0943, 0.0127, 0.1586, -0.0078, 0.0140, 0.1526, 0.3097,
        0.0859, 0.1718, 0.0627, 0.1522, 0.0702, -0.0749, 0.0974, 0.2796,
        0.1892, 0.0992, 0.1424, 0.0823, -0.0393, 0.1633, 0.1756, 0.0010,
        0.0441, 0.0227, 0.0333, 0.0414, 0.2010, 0.0571, 0.0584, 0.0978,
        -0.0359, 0.1084, 0.1028, 0.0069, 0.0199, 0.0887, -0.0002, 0.1195,
        0.0744, -0.0014, -0.1112, 0.0396, -0.0116, 0.0394  # Through 2023
    ],
    "cash": [
        # 3-Month T-Bill returns (proxy for cash)
        0.0308, 0.0316, 0.0455, 0.0231, 0.0107, 0.0030, 0.0032, 0.0014,
        0.0002, 0.0003, 0.0003, 0.0006, 0.0038, 0.0033, 0.0038, 0.0038,
        0.0038, 0.0101, 0.0181, 0.0295, 0.0261, 0.0149, 0.0116, 0.0157,
        0.0253, 0.0293, 0.0090, 0.0154, 0.0273, 0.0258, 0.0292, 0.0393,
        0.0316, 0.0249, 0.0249, 0.0352, 0.0393, 0.0429, 0.0387, 0.0516,
        0.0583, 0.0572, 0.0545, 0.0430, 0.0299, 0.0280, 0.0358, 0.0595,
        0.0527, 0.0508, 0.0570, 0.0598, 0.0341, 0.0300, 0.0509, 0.0516,
        0.0501, 0.0525, 0.0480, 0.0455, 0.0552, 0.0349, 0.0154, 0.0116,
        0.0297, 0.0451, 0.0479, 0.0141, 0.0011, 0.0010, 0.0010, 0.0005,
        0.0007, 0.0002, 0.0002, 0.0021, 0.0094, 0.0198, 0.0473, 0.0486,
        0.0013, 0.0055, 0.0033, 0.0303, 0.0416, 0.0524  # Through 2023
    ]
}

