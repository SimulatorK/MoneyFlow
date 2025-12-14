from sqlalchemy import Column, Integer, Float, String, ForeignKey, Boolean
from app.models import Base

class IncomeTaxes(Base):
    __tablename__ = "income_taxes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Tax year for calculations
    tax_year = Column(Integer, default=2025)
    
    # Filing status
    filing_status = Column(String, default="married_filing_jointly")
    filing_state = Column(String, default="MO")  # State for state income tax
    
    # Base income
    base_salary = Column(Float)
    pay_frequency = Column(String)
    
    # Optional investment income (annual)
    short_term_cap_gains = Column(Float, default=0)
    dividends_interest = Column(Float, default=0)
    long_term_cap_gains = Column(Float, default=0)
    
    # ISO Stock Options (for AMT calculation)
    iso_shares_exercised = Column(Integer, default=0)
    iso_strike_price = Column(Float, default=0)
    iso_fmv_at_exercise = Column(Float, default=0)
    
    # Pretax deductions (per pay period)
    health_insurance_per_pay = Column(Float, default=0)
    dental_per_pay = Column(Float, default=0)
    vision_per_pay = Column(Float, default=0)
    
    # Retirement contributions
    traditional_401k = Column(Float)
    traditional_401k_type = Column(String)
    roth_401k = Column(Float)
    roth_401k_type = Column(String)
    after_tax_401k = Column(Float)
    after_tax_401k_type = Column(String)
    traditional_ira = Column(Float)
    traditional_ira_type = Column(String)
    roth_ira = Column(Float)
    roth_ira_type = Column(String)
    spousal_ira = Column(Float)
    spousal_ira_type = Column(String)
    spousal_roth_ira = Column(Float)
    spousal_roth_ira_type = Column(String)
    employer_401k = Column(Float)
    employer_401k_type = Column(String)
