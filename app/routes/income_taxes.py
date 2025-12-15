"""
Income and tax calculation routes for MoneyFlow application.

This module provides comprehensive tax calculation functionality including:
- Federal income tax (progressive brackets 2023-2026)
- State income tax (Missouri specific, with framework for others)
- FICA taxes (Social Security and Medicare)
- Alternative Minimum Tax (AMT) calculations
- Capital gains (short-term and long-term)
- ISO stock option tax implications

Tax Features:
- Multi-year tax bracket support (2023-2026)
- All filing statuses (Single, MFJ, MFS, HOH)
- Standard and itemized deduction support
- Pre-tax deduction handling (401k, HSA, health insurance)
- Per-pay-period breakdown for paycheck planning

Calculation Functions:
- calculate_federal_tax_with_breakdown(): Progressive federal tax
- calculate_missouri_tax_with_breakdown(): Missouri state tax
- calculate_fica(): Social Security and Medicare taxes
- calculate_amt(): Alternative Minimum Tax
- calculate_taxes(): Full tax calculation pipeline

Routes:
    GET  /income-taxes  - Income and tax configuration page
    POST /income-taxes  - Save income/tax data and recalculate

Note: Tax calculations are estimates and should not be used as
professional tax advice. Always consult a tax professional.
"""

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
from app.models.income_taxes import IncomeTaxes
from app.logging_config import get_logger
import base64

# Module logger for income and tax operations
logger = get_logger(__name__)

# Router and template configuration
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_profile_picture_data(user):
    """Get base64 encoded profile picture data for templates."""
    if user and user.profile_picture and user.profile_picture_type:
        return base64.b64encode(user.profile_picture).decode('utf-8'), user.profile_picture_type
    return None, None

# Constants
PAY_FREQUENCIES = ["weekly", "bi-weekly", "semi-monthly", "monthly"]
PAY_PERIODS_PER_YEAR = {"weekly": 52, "bi-weekly": 26, "semi-monthly": 24, "monthly": 12}

FILING_STATUSES = [
    ("married_filing_jointly", "Married Filing Jointly"),
    ("married_filing_separately", "Married Filing Separately"),
    ("single", "Single"),
    ("head_of_household", "Head of Household"),
]

# Supported states for tax calculation
FILING_STATES = [
    ("MO", "Missouri"),
    ("CA", "California"),
]

TAX_YEARS = [2023, 2024, 2025, 2026]

CONTRIBS = [
    ("traditional_401k", "Traditional 401k"),
    ("roth_401k", "Roth 401k"),
    ("after_tax_401k", "After-Tax 401k"),
    ("traditional_ira", "Traditional IRA"),
    ("roth_ira", "Roth IRA"),
    ("spousal_ira", "Spousal Traditional IRA"),
    ("spousal_roth_ira", "Spousal Roth IRA"),
    ("employer_401k", "Employer 401k (match/based on salary)")
]

# ==================== TAX DATA BY YEAR ====================
# All tax brackets, deductions, and limits organized by year

TAX_DATA = {
    2023: {
        "federal_brackets": {
            "married_filing_jointly": [
                (22000, 0.10), (89450, 0.12), (190750, 0.22), (364200, 0.24),
                (462500, 0.32), (693750, 0.35), (float('inf'), 0.37),
            ],
            "married_filing_separately": [
                (11000, 0.10), (44725, 0.12), (95375, 0.22), (182100, 0.24),
                (231250, 0.32), (346875, 0.35), (float('inf'), 0.37),
            ],
            "single": [
                (11000, 0.10), (44725, 0.12), (95375, 0.22), (182100, 0.24),
                (231250, 0.32), (578125, 0.35), (float('inf'), 0.37),
            ],
            "head_of_household": [
                (15700, 0.10), (59850, 0.12), (95350, 0.22), (182100, 0.24),
                (231250, 0.32), (578100, 0.35), (float('inf'), 0.37),
            ],
        },
        "standard_deductions": {
            "married_filing_jointly": 27700,
            "married_filing_separately": 13850,
            "single": 13850,
            "head_of_household": 20800,
        },
        "ltcg_brackets": {
            "married_filing_jointly": [(89250, 0.0), (553850, 0.15), (float('inf'), 0.20)],
            "married_filing_separately": [(44625, 0.0), (276900, 0.15), (float('inf'), 0.20)],
            "single": [(44625, 0.0), (492300, 0.15), (float('inf'), 0.20)],
            "head_of_household": [(59750, 0.0), (523050, 0.15), (float('inf'), 0.20)],
        },
        "ss_wage_base": 160200,
        "amt_exemption": {
            "married_filing_jointly": 126500, "married_filing_separately": 63250,
            "single": 81300, "head_of_household": 81300,
        },
        "amt_phaseout_start": {
            "married_filing_jointly": 1156300, "married_filing_separately": 578150,
            "single": 578150, "head_of_household": 578150,
        },
        "amt_rate_threshold": {
            "married_filing_jointly": 220700, "married_filing_separately": 110350,
            "single": 220700, "head_of_household": 220700,
        },
        "mo_brackets": [
            (1121, 0.00), (2242, 0.02), (3363, 0.025), (4484, 0.03),
            (5605, 0.035), (6726, 0.04), (7847, 0.045), (float('inf'), 0.0495),
        ],
        "mo_standard_deductions": {
            "married_filing_jointly": 27700, "married_filing_separately": 13850,
            "single": 13850, "head_of_household": 20800,
        },
        # California tax brackets (2023)
        "ca_brackets": {
            "married_filing_jointly": [
                (20198, 0.01), (47884, 0.02), (75576, 0.04), (104910, 0.06),
                (132590, 0.08), (677278, 0.093), (812728, 0.103), (1354550, 0.113),
                (float('inf'), 0.123),
            ],
            "married_filing_separately": [
                (10099, 0.01), (23942, 0.02), (37788, 0.04), (52455, 0.06),
                (66295, 0.08), (338639, 0.093), (406364, 0.103), (677275, 0.113),
                (float('inf'), 0.123),
            ],
            "single": [
                (10099, 0.01), (23942, 0.02), (37788, 0.04), (52455, 0.06),
                (66295, 0.08), (338639, 0.093), (406364, 0.103), (677275, 0.113),
                (float('inf'), 0.123),
            ],
            "head_of_household": [
                (20212, 0.01), (47887, 0.02), (61730, 0.04), (76397, 0.06),
                (90240, 0.08), (460547, 0.093), (552658, 0.103), (921095, 0.113),
                (float('inf'), 0.123),
            ],
        },
        "ca_standard_deductions": {
            "married_filing_jointly": 10726, "married_filing_separately": 5363,
            "single": 5363, "head_of_household": 10726,
        },
        "ca_mental_health_threshold": 1000000,  # 1% surcharge over $1M
    },
    2024: {
        "federal_brackets": {
            "married_filing_jointly": [
                (23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24),
                (487450, 0.32), (731200, 0.35), (float('inf'), 0.37),
            ],
            "married_filing_separately": [
                (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
                (243725, 0.32), (365600, 0.35), (float('inf'), 0.37),
            ],
            "single": [
                (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
                (243725, 0.32), (609350, 0.35), (float('inf'), 0.37),
            ],
            "head_of_household": [
                (16550, 0.10), (63100, 0.12), (100500, 0.22), (191950, 0.24),
                (243700, 0.32), (609350, 0.35), (float('inf'), 0.37),
            ],
        },
        "standard_deductions": {
            "married_filing_jointly": 29200,
            "married_filing_separately": 14600,
            "single": 14600,
            "head_of_household": 21900,
        },
        "ltcg_brackets": {
            "married_filing_jointly": [(94050, 0.0), (583750, 0.15), (float('inf'), 0.20)],
            "married_filing_separately": [(47025, 0.0), (291850, 0.15), (float('inf'), 0.20)],
            "single": [(47025, 0.0), (518900, 0.15), (float('inf'), 0.20)],
            "head_of_household": [(63000, 0.0), (551350, 0.15), (float('inf'), 0.20)],
        },
        "ss_wage_base": 168600,
        "amt_exemption": {
            "married_filing_jointly": 133300, "married_filing_separately": 66650,
            "single": 85700, "head_of_household": 85700,
        },
        "amt_phaseout_start": {
            "married_filing_jointly": 1218700, "married_filing_separately": 609350,
            "single": 609350, "head_of_household": 609350,
        },
        "amt_rate_threshold": {
            "married_filing_jointly": 232600, "married_filing_separately": 116300,
            "single": 232600, "head_of_household": 232600,
        },
        "mo_brackets": [
            (1207, 0.00), (2414, 0.02), (3621, 0.025), (4828, 0.03),
            (6035, 0.035), (7242, 0.04), (8449, 0.045), (float('inf'), 0.049),
        ],
        "mo_standard_deductions": {
            "married_filing_jointly": 29200, "married_filing_separately": 14600,
            "single": 14600, "head_of_household": 21900,
        },
        # California tax brackets (2024)
        "ca_brackets": {
            "married_filing_jointly": [
                (20824, 0.01), (49368, 0.02), (77918, 0.04), (108162, 0.06),
                (136700, 0.08), (698274, 0.093), (837922, 0.103), (1396542, 0.113),
                (float('inf'), 0.123),
            ],
            "married_filing_separately": [
                (10412, 0.01), (24684, 0.02), (38959, 0.04), (54081, 0.06),
                (68350, 0.08), (349137, 0.093), (418961, 0.103), (698271, 0.113),
                (float('inf'), 0.123),
            ],
            "single": [
                (10412, 0.01), (24684, 0.02), (38959, 0.04), (54081, 0.06),
                (68350, 0.08), (349137, 0.093), (418961, 0.103), (698271, 0.113),
                (float('inf'), 0.123),
            ],
            "head_of_household": [
                (20839, 0.01), (49371, 0.02), (63644, 0.04), (78765, 0.06),
                (93037, 0.08), (474824, 0.093), (569790, 0.103), (949649, 0.113),
                (float('inf'), 0.123),
            ],
        },
        "ca_standard_deductions": {
            "married_filing_jointly": 11056, "married_filing_separately": 5528,
            "single": 5528, "head_of_household": 11056,
        },
        "ca_mental_health_threshold": 1000000,
    },
    2025: {
        "federal_brackets": {
            "married_filing_jointly": [
                (23850, 0.10), (96950, 0.12), (206700, 0.22), (394600, 0.24),
                (501050, 0.32), (751600, 0.35), (float('inf'), 0.37),
            ],
            "married_filing_separately": [
                (11925, 0.10), (48475, 0.12), (103350, 0.22), (197300, 0.24),
                (250525, 0.32), (375800, 0.35), (float('inf'), 0.37),
            ],
            "single": [
                (11925, 0.10), (48475, 0.12), (103350, 0.22), (197300, 0.24),
                (250525, 0.32), (626350, 0.35), (float('inf'), 0.37),
            ],
            "head_of_household": [
                (17000, 0.10), (64850, 0.12), (103350, 0.22), (197300, 0.24),
                (250500, 0.32), (626350, 0.35), (float('inf'), 0.37),
            ],
        },
        "standard_deductions": {
            "married_filing_jointly": 30000,
            "married_filing_separately": 15000,
            "single": 15000,
            "head_of_household": 22500,
        },
        "ltcg_brackets": {
            "married_filing_jointly": [(96700, 0.0), (600050, 0.15), (float('inf'), 0.20)],
            "married_filing_separately": [(48350, 0.0), (300025, 0.15), (float('inf'), 0.20)],
            "single": [(48350, 0.0), (533400, 0.15), (float('inf'), 0.20)],
            "head_of_household": [(64750, 0.0), (566700, 0.15), (float('inf'), 0.20)],
        },
        "ss_wage_base": 174900,
        "amt_exemption": {
            "married_filing_jointly": 137000, "married_filing_separately": 68500,
            "single": 88100, "head_of_household": 88100,
        },
        "amt_phaseout_start": {
            "married_filing_jointly": 1252700, "married_filing_separately": 626350,
            "single": 626350, "head_of_household": 626350,
        },
        "amt_rate_threshold": {
            "married_filing_jointly": 239100, "married_filing_separately": 119550,
            "single": 239100, "head_of_household": 239100,
        },
        "mo_brackets": [
            (1236, 0.00), (2472, 0.02), (3708, 0.025), (4944, 0.03),
            (6180, 0.035), (7416, 0.04), (8652, 0.045), (float('inf'), 0.048),
        ],
        "mo_standard_deductions": {
            "married_filing_jointly": 30000, "married_filing_separately": 15000,
            "single": 15000, "head_of_household": 22500,
        },
        # California tax brackets (2025 - estimated based on inflation adjustments)
        "ca_brackets": {
            "married_filing_jointly": [
                (21450, 0.01), (50850, 0.02), (80260, 0.04), (111410, 0.06),
                (140800, 0.08), (719220, 0.093), (863060, 0.103), (1438440, 0.113),
                (float('inf'), 0.123),
            ],
            "married_filing_separately": [
                (10725, 0.01), (25425, 0.02), (40130, 0.04), (55705, 0.06),
                (70400, 0.08), (359610, 0.093), (431530, 0.103), (719220, 0.113),
                (float('inf'), 0.123),
            ],
            "single": [
                (10725, 0.01), (25425, 0.02), (40130, 0.04), (55705, 0.06),
                (70400, 0.08), (359610, 0.093), (431530, 0.103), (719220, 0.113),
                (float('inf'), 0.123),
            ],
            "head_of_household": [
                (21465, 0.01), (50855, 0.02), (65555, 0.04), (81130, 0.06),
                (95830, 0.08), (489070, 0.093), (586890, 0.103), (978140, 0.113),
                (float('inf'), 0.123),
            ],
        },
        "ca_standard_deductions": {
            "married_filing_jointly": 11390, "married_filing_separately": 5695,
            "single": 5695, "head_of_household": 11390,
        },
        "ca_mental_health_threshold": 1000000,
    },
    2026: {
        "federal_brackets": {
            "married_filing_jointly": [
                (24800, 0.10), (100800, 0.12), (211400, 0.22), (403550, 0.24),
                (512450, 0.32), (768700, 0.35), (float('inf'), 0.37),
            ],
            "married_filing_separately": [
                (12250, 0.10), (49975, 0.12), (106375, 0.22), (202825, 0.24),
                (257525, 0.32), (386400, 0.35), (float('inf'), 0.37),
            ],
            "single": [
                (12250, 0.10), (49975, 0.12), (106375, 0.22), (202825, 0.24),
                (257525, 0.32), (591300, 0.35), (float('inf'), 0.37),
            ],
            "head_of_household": [
                (17500, 0.10), (67050, 0.12), (106375, 0.22), (202825, 0.24),
                (257525, 0.32), (591300, 0.35), (float('inf'), 0.37),
            ],
        },
        "standard_deductions": {
            "married_filing_jointly": 32200,
            "married_filing_separately": 16100,
            "single": 16100,
            "head_of_household": 24200,
        },
        "ltcg_brackets": {
            "married_filing_jointly": [(96700, 0.0), (600050, 0.15), (float('inf'), 0.20)],
            "married_filing_separately": [(48350, 0.0), (300025, 0.15), (float('inf'), 0.20)],
            "single": [(48350, 0.0), (533400, 0.15), (float('inf'), 0.20)],
            "head_of_household": [(64750, 0.0), (566700, 0.15), (float('inf'), 0.20)],
        },
        "ss_wage_base": 176100,
        "amt_exemption": {
            "married_filing_jointly": 137000, "married_filing_separately": 68500,
            "single": 88100, "head_of_household": 88100,
        },
        "amt_phaseout_start": {
            "married_filing_jointly": 1218700, "married_filing_separately": 609350,
            "single": 609350, "head_of_household": 609350,
        },
        "amt_rate_threshold": {
            "married_filing_jointly": 232600, "married_filing_separately": 116300,
            "single": 232600, "head_of_household": 232600,
        },
        "mo_brackets": [
            (1236, 0.00), (2472, 0.02), (3708, 0.025), (4944, 0.03),
            (6180, 0.035), (7416, 0.04), (8652, 0.045), (float('inf'), 0.048),
        ],
        "mo_standard_deductions": {
            "married_filing_jointly": 32200, "married_filing_separately": 16100,
            "single": 16100, "head_of_household": 24200,
        },
        # California tax brackets (2026 - estimated based on inflation adjustments)
        "ca_brackets": {
            "married_filing_jointly": [
                (22100, 0.01), (52380, 0.02), (82670, 0.04), (114750, 0.06),
                (145020, 0.08), (740800, 0.093), (888950, 0.103), (1481600, 0.113),
                (float('inf'), 0.123),
            ],
            "married_filing_separately": [
                (11050, 0.01), (26190, 0.02), (41335, 0.04), (57375, 0.06),
                (72510, 0.08), (370400, 0.093), (444475, 0.103), (740800, 0.113),
                (float('inf'), 0.123),
            ],
            "single": [
                (11050, 0.01), (26190, 0.02), (41335, 0.04), (57375, 0.06),
                (72510, 0.08), (370400, 0.093), (444475, 0.103), (740800, 0.113),
                (float('inf'), 0.123),
            ],
            "head_of_household": [
                (22115, 0.01), (52380, 0.02), (67525, 0.04), (83565, 0.06),
                (98705, 0.08), (503740, 0.093), (604500, 0.103), (1007580, 0.113),
                (float('inf'), 0.123),
            ],
        },
        "ca_standard_deductions": {
            "married_filing_jointly": 11730, "married_filing_separately": 5865,
            "single": 5865, "head_of_household": 11730,
        },
        "ca_mental_health_threshold": 1000000,
    },
}

# FICA constants (relatively stable across years)
SS_RATE = 0.062
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ADDITIONAL_MEDICARE_THRESHOLD = {
    "married_filing_jointly": 250000,
    "married_filing_separately": 125000,
    "single": 200000,
    "head_of_household": 200000,
}


def get_tax_year_data(tax_year):
    """Get tax data for a specific year, defaulting to 2025 if not found."""
    return TAX_DATA.get(tax_year, TAX_DATA[2025])


def get_contribution_amount(value, contrib_type, salary):
    """Convert contribution to dollar amount (handles % or $)."""
    if contrib_type == "%":
        return salary * (value / 100.0)
    return value


def calculate_federal_tax_with_breakdown(taxable_income, filing_status, tax_year):
    """Calculate federal income tax using progressive brackets, with per-bracket breakdown."""
    year_data = get_tax_year_data(tax_year)
    brackets = year_data["federal_brackets"].get(filing_status, year_data["federal_brackets"]["single"])
    tax = 0.0
    prev_limit = 0
    breakdown = []
    for limit, rate in brackets:
        if taxable_income <= prev_limit:
            breakdown.append((limit, rate, 0, 0))
        else:
            taxable_in_bracket = min(taxable_income, limit) - prev_limit
            tax_in_bracket = taxable_in_bracket * rate
            tax += tax_in_bracket
            breakdown.append((limit, rate, taxable_in_bracket, tax_in_bracket))
        prev_limit = limit
    return tax, breakdown


def calculate_ltcg_tax(ltcg, taxable_income, filing_status, tax_year):
    """Calculate long-term capital gains tax."""
    year_data = get_tax_year_data(tax_year)
    brackets = year_data["ltcg_brackets"].get(filing_status, year_data["ltcg_brackets"]["single"])
    total_income = taxable_income + ltcg
    tax = 0.0
    prev_limit = 0
    remaining_ltcg = ltcg
    for limit, rate in brackets:
        if remaining_ltcg <= 0:
            break
        bracket_start = max(prev_limit, taxable_income)
        if total_income <= prev_limit:
            prev_limit = limit
            continue
        bracket_amount = min(total_income, limit) - bracket_start
        bracket_amount = max(0, min(bracket_amount, remaining_ltcg))
        tax += bracket_amount * rate
        remaining_ltcg -= bracket_amount
        prev_limit = limit
    return tax


def calculate_missouri_tax_with_breakdown(mo_taxable_income, tax_year):
    """Calculate Missouri state income tax, with per-bracket breakdown."""
    year_data = get_tax_year_data(tax_year)
    mo_brackets = year_data["mo_brackets"]
    tax = 0.0
    prev_limit = 0
    breakdown = []
    for limit, rate in mo_brackets:
        if mo_taxable_income <= prev_limit:
            breakdown.append((limit, rate, 0, 0))
        else:
            taxable_in_bracket = min(mo_taxable_income, limit) - prev_limit
            tax_in_bracket = taxable_in_bracket * rate
            tax += tax_in_bracket
            breakdown.append((limit, rate, taxable_in_bracket, tax_in_bracket))
        prev_limit = limit
    return tax, breakdown


def calculate_california_tax_with_breakdown(ca_taxable_income, filing_status, tax_year):
    """
    Calculate California state income tax, with per-bracket breakdown.
    
    California has:
    - Progressive income tax brackets (1% to 12.3%)
    - Mental Health Services Tax: 1% surcharge on income over $1 million
    - No city income taxes in California (unlike some states)
    
    Args:
        ca_taxable_income: California taxable income (after standard deduction)
        filing_status: Tax filing status
        tax_year: Tax year for rate lookup
        
    Returns:
        Tuple of (total_tax, bracket_breakdown, mental_health_tax)
    """
    year_data = get_tax_year_data(tax_year)
    ca_brackets = year_data.get("ca_brackets", {}).get(filing_status, 
                   year_data.get("ca_brackets", {}).get("single", []))
    mental_health_threshold = year_data.get("ca_mental_health_threshold", 1000000)
    
    if not ca_brackets:
        return 0, [], 0
    
    tax = 0.0
    prev_limit = 0
    breakdown = []
    
    for limit, rate in ca_brackets:
        if ca_taxable_income <= prev_limit:
            breakdown.append((limit, rate, 0, 0))
        else:
            taxable_in_bracket = min(ca_taxable_income, limit) - prev_limit
            tax_in_bracket = taxable_in_bracket * rate
            tax += tax_in_bracket
            breakdown.append((limit, rate, taxable_in_bracket, tax_in_bracket))
        prev_limit = limit
    
    # Mental Health Services Tax (1% on income over $1M)
    mental_health_tax = 0
    if ca_taxable_income > mental_health_threshold:
        mental_health_tax = (ca_taxable_income - mental_health_threshold) * 0.01
    
    total_tax = tax + mental_health_tax
    
    return total_tax, breakdown, mental_health_tax


def calculate_state_tax(agi, filing_status, filing_state, tax_year):
    """
    Calculate state income tax for the specified state.
    
    Args:
        agi: Adjusted Gross Income
        filing_status: Tax filing status
        filing_state: Two-letter state code (e.g., 'MO', 'CA')
        tax_year: Tax year for rate lookup
        
    Returns:
        Dictionary with state tax details
    """
    year_data = get_tax_year_data(tax_year)
    
    if filing_state == "MO":
        mo_standard_deduction = year_data["mo_standard_deductions"].get(filing_status, 15175)
        mo_taxable_income = max(0, agi - mo_standard_deduction)
        state_tax, state_breakdown = calculate_missouri_tax_with_breakdown(mo_taxable_income, tax_year)
        return {
            "state": "Missouri",
            "state_code": "MO",
            "standard_deduction": mo_standard_deduction,
            "taxable_income": mo_taxable_income,
            "state_tax": state_tax,
            "state_breakdown": state_breakdown,
            "brackets": year_data["mo_brackets"],
            "mental_health_tax": 0,
            "city_tax": 0,
            "city_name": None,
        }
    
    elif filing_state == "CA":
        ca_standard_deduction = year_data.get("ca_standard_deductions", {}).get(filing_status, 5695)
        ca_taxable_income = max(0, agi - ca_standard_deduction)
        state_tax, state_breakdown, mental_health_tax = calculate_california_tax_with_breakdown(
            ca_taxable_income, filing_status, tax_year
        )
        return {
            "state": "California",
            "state_code": "CA",
            "standard_deduction": ca_standard_deduction,
            "taxable_income": ca_taxable_income,
            "state_tax": state_tax,
            "state_breakdown": state_breakdown,
            "brackets": year_data.get("ca_brackets", {}).get(filing_status, []),
            "mental_health_tax": mental_health_tax,
            "city_tax": 0,  # California has no city income tax
            "city_name": None,
        }
    
    else:
        # Default: no state tax calculation
        return {
            "state": "Unknown",
            "state_code": filing_state,
            "standard_deduction": 0,
            "taxable_income": 0,
            "state_tax": 0,
            "state_breakdown": [],
            "brackets": [],
            "mental_health_tax": 0,
            "city_tax": 0,
            "city_name": None,
        }


def calculate_fica(wages, filing_status, tax_year):
    """Calculate FICA taxes (Social Security + Medicare)."""
    year_data = get_tax_year_data(tax_year)
    ss_wage_base = year_data["ss_wage_base"]
    ss_wages = min(wages, ss_wage_base)
    social_security = ss_wages * SS_RATE
    medicare = wages * MEDICARE_RATE
    threshold = ADDITIONAL_MEDICARE_THRESHOLD.get(filing_status, 200000)
    if wages > threshold:
        additional_medicare = (wages - threshold) * ADDITIONAL_MEDICARE_RATE
    else:
        additional_medicare = 0
    return {
        "social_security": social_security,
        "medicare": medicare,
        "additional_medicare": additional_medicare,
        "total_fica": social_security + medicare + additional_medicare,
        "ss_wage_base": ss_wage_base
    }


def calculate_iso_bargain_element(shares, strike_price, fmv):
    """Calculate the bargain element from ISO exercise for AMT."""
    if shares <= 0 or fmv <= strike_price:
        return 0
    return shares * (fmv - strike_price)


def calculate_amt(amti, filing_status, tax_year):
    """Calculate Alternative Minimum Tax."""
    year_data = get_tax_year_data(tax_year)
    exemption = year_data["amt_exemption"].get(filing_status, 88100)
    phaseout_start = year_data["amt_phaseout_start"].get(filing_status, 609350)
    
    if amti > phaseout_start:
        exemption_reduction = (amti - phaseout_start) * 0.25
        exemption = max(0, exemption - exemption_reduction)
    
    amt_taxable = max(0, amti - exemption)
    rate_threshold = year_data["amt_rate_threshold"].get(filing_status, 232600)
    
    if amt_taxable <= rate_threshold:
        amt = amt_taxable * 0.26
    else:
        amt = (rate_threshold * 0.26) + ((amt_taxable - rate_threshold) * 0.28)
    
    return {
        "amti": amti,
        "exemption": exemption,
        "amt_taxable": amt_taxable,
        "amt": amt,
        "rate_26_amount": min(amt_taxable, rate_threshold),
        "rate_28_amount": max(0, amt_taxable - rate_threshold)
    }


def calculate_taxes(data, tax_year=None):
    """Perform full tax calculation and return a dict of results."""
    if not data or not data.base_salary:
        return None
    
    if tax_year is None:
        tax_year = getattr(data, 'tax_year', 2025) or 2025
    
    year_data = get_tax_year_data(tax_year)
    
    filing_status = data.filing_status or "married_filing_jointly"
    filing_state = data.filing_state or "MO"
    salary = data.base_salary or 0
    pay_frequency = data.pay_frequency or "bi-weekly"
    pay_periods = PAY_PERIODS_PER_YEAR.get(pay_frequency, 26)
    
    # Investment income
    stcg = data.short_term_cap_gains or 0
    dividends = data.dividends_interest or 0
    ltcg = data.long_term_cap_gains or 0
    
    # ISO Stock Options
    iso_shares = data.iso_shares_exercised or 0
    iso_strike = data.iso_strike_price or 0
    iso_fmv = data.iso_fmv_at_exercise or 0
    iso_bargain_element = calculate_iso_bargain_element(iso_shares, iso_strike, iso_fmv)
    
    # Pretax deductions (annualize)
    health_annual = (data.health_insurance_per_pay or 0) * pay_periods
    dental_annual = (data.dental_per_pay or 0) * pay_periods
    vision_annual = (data.vision_per_pay or 0) * pay_periods
    pretax_deductions_annual = health_annual + dental_annual + vision_annual
    
    # Retirement contributions (convert % to $) - track each individually
    trad_401k = get_contribution_amount(data.traditional_401k or 0, data.traditional_401k_type or "$", salary)
    roth_401k = get_contribution_amount(data.roth_401k or 0, data.roth_401k_type or "$", salary)
    after_tax_401k = get_contribution_amount(data.after_tax_401k or 0, data.after_tax_401k_type or "$", salary)
    trad_ira = get_contribution_amount(data.traditional_ira or 0, data.traditional_ira_type or "$", salary)
    roth_ira = get_contribution_amount(data.roth_ira or 0, data.roth_ira_type or "$", salary)
    spousal_trad_ira = get_contribution_amount(data.spousal_ira or 0, data.spousal_ira_type or "$", salary)
    spousal_roth_ira = get_contribution_amount(data.spousal_roth_ira or 0, data.spousal_roth_ira_type or "$", salary)
    employer_401k = get_contribution_amount(data.employer_401k or 0, data.employer_401k_type or "$", salary)
    
    # Pre-tax retirement (reduces taxable income)
    pretax_retirement = trad_401k + trad_ira + spousal_trad_ira
    
    # After-tax retirement (does not reduce taxable income)
    aftertax_retirement = roth_401k + after_tax_401k + roth_ira + spousal_roth_ira
    
    # Total employee contributions (excludes employer match)
    employee_contributions = pretax_retirement + aftertax_retirement
    
    # Total including employer
    total_retirement_with_employer = employee_contributions + employer_401k
    
    # Gross income (salary + investment income)
    gross_income = salary + stcg + dividends + ltcg
    
    # Wages for FICA (salary only, minus pretax deductions like health)
    fica_wages = salary - pretax_deductions_annual
    
    # AGI = Gross income - traditional 401k/IRA (pretax deductions don't reduce AGI, they reduce W-2)
    agi = salary + stcg + dividends + ltcg - pretax_retirement
    
    # MAGI (for most purposes, same as AGI)
    magi = agi
    
    # Federal standard deduction
    standard_deduction = year_data["standard_deductions"].get(filing_status, 16100)
    
    # Itemized deductions (sum of all itemizable deductions)
    mortgage_interest = getattr(data, 'mortgage_interest_deduction', 0) or 0
    property_taxes = getattr(data, 'property_tax_deduction', 0) or 0
    charitable = getattr(data, 'charitable_deduction', 0) or 0
    student_loan_int = min(getattr(data, 'student_loan_interest', 0) or 0, 2500)  # Cap at $2,500
    other_deductions = getattr(data, 'other_deductions', 0) or 0
    
    # SALT cap ($10,000 for property taxes)
    salt_capped = min(property_taxes, 10000)
    
    # Total itemized deductions
    itemized_deductions = mortgage_interest + salt_capped + charitable + other_deductions
    
    # Use itemized if user chose it AND itemized > standard, otherwise use standard
    use_itemized = getattr(data, 'use_itemized', False) or False
    if use_itemized and itemized_deductions > standard_deduction:
        deduction_used = itemized_deductions
        deduction_type = "itemized"
    else:
        deduction_used = standard_deduction
        deduction_type = "standard"
    
    # Student loan interest is "above the line" (reduces AGI, not itemized)
    above_the_line_deductions = student_loan_int
    agi_after_above_line = agi - above_the_line_deductions
    
    # Taxable ordinary income (excluding LTCG which is taxed separately)
    ordinary_income = salary + stcg + dividends - pretax_deductions_annual - pretax_retirement - above_the_line_deductions
    taxable_ordinary = max(0, ordinary_income - deduction_used)
    
    # Regular Federal income tax on ordinary income (with breakdown)
    federal_tax_ordinary, federal_breakdown = calculate_federal_tax_with_breakdown(taxable_ordinary, filing_status, tax_year)
    
    # LTCG tax (taxed at preferential rates)
    ltcg_tax = calculate_ltcg_tax(ltcg, taxable_ordinary, filing_status, tax_year)
    
    # Regular tax (before AMT comparison)
    regular_tax = federal_tax_ordinary + ltcg_tax
    
    # AMT Calculation
    # For AMT, we start with AGI (not taxable income after standard deduction)
    # Then add back preference items like ISO bargain element
    # The AMT exemption (applied in calculate_amt) replaces the standard deduction
    # Note: LTCG is taxed at preferential rates under both regular tax and AMT
    amti = agi + iso_bargain_element
    amt_result = calculate_amt(amti, filing_status, tax_year)
    
    # Calculate tentative minimum tax (AMT on ordinary + preferential LTCG rate)
    # For proper AMT calculation with LTCG, the tentative minimum tax should be:
    # AMT on (AMTI - LTCG) + LTCG tax at preferential rates
    amt_ordinary_portion = max(0, amti - ltcg)
    amt_on_ordinary = calculate_amt(amt_ordinary_portion, filing_status, tax_year)["amt"]
    tentative_minimum_tax = amt_on_ordinary + ltcg_tax
    
    # The AMT is the excess of tentative minimum tax over regular tax
    # You pay regular tax + AMT (if any)
    amt_applies = tentative_minimum_tax > regular_tax
    federal_tax_before_credits = max(regular_tax, tentative_minimum_tax)
    amt_owed = tentative_minimum_tax - regular_tax if amt_applies else 0
    
    # Tax Credits (reduce taxes owed, not taxable income)
    child_credit = getattr(data, 'child_tax_credit', 0) or 0
    education_credits = getattr(data, 'education_credits', 0) or 0
    other_credits = getattr(data, 'other_credits', 0) or 0
    total_credits = child_credit + education_credits + other_credits
    
    # Apply credits (cannot reduce tax below $0)
    total_federal_tax = max(0, federal_tax_before_credits - total_credits)
    
    # Update amt_result with tentative minimum tax for display
    amt_result["tentative_minimum_tax"] = tentative_minimum_tax
    
    # FICA on wages
    fica = calculate_fica(fica_wages, filing_status, tax_year)
    
    # State Tax (using unified state tax function)
    state_tax_result = calculate_state_tax(agi, filing_status, filing_state, tax_year)
    state_tax = state_tax_result["state_tax"]
    state_standard_deduction = state_tax_result["standard_deduction"]
    state_taxable_income = state_tax_result["taxable_income"]
    state_breakdown = state_tax_result["state_breakdown"]
    state_brackets = state_tax_result["brackets"]
    mental_health_tax = state_tax_result.get("mental_health_tax", 0)
    city_tax = state_tax_result.get("city_tax", 0)
    
    # Backward compatibility - keep mo_* variables for templates
    mo_standard_deduction = state_standard_deduction
    mo_taxable_income = state_taxable_income
    mo_state_tax = state_tax
    mo_breakdown = state_breakdown
    
    # Total taxes (federal + state + FICA)
    total_taxes = total_federal_tax + fica["total_fica"] + state_tax
    
    # Per paycheck calculations
    federal_tax_per_pay = total_federal_tax / pay_periods
    state_tax_per_pay = state_tax / pay_periods
    fica_per_pay = fica["total_fica"] / pay_periods
    total_tax_per_pay = total_taxes / pay_periods
    
    # Gross pay per paycheck (salary portion only)
    gross_per_pay = salary / pay_periods
    
    # Net paycheck
    pretax_deductions_per_pay = (data.health_insurance_per_pay or 0) + (data.dental_per_pay or 0) + (data.vision_per_pay or 0)
    pretax_retirement_per_pay = pretax_retirement / pay_periods
    aftertax_retirement_per_pay = aftertax_retirement / pay_periods
    net_per_pay = gross_per_pay - federal_tax_per_pay - state_tax_per_pay - fica_per_pay - pretax_deductions_per_pay - pretax_retirement_per_pay - aftertax_retirement_per_pay
    
    tax_rate = (total_taxes / gross_income * 100) if gross_income > 0 else 0
    federal_rate = (total_federal_tax / gross_income * 100) if gross_income > 0 else 0
    state_rate = (state_tax / gross_income * 100) if gross_income > 0 else 0
    fica_rate = (fica["total_fica"] / gross_income * 100) if gross_income > 0 else 0
    
    # Tax brackets with breakdown for display
    federal_brackets = year_data["federal_brackets"].get(filing_status, year_data["federal_brackets"]["single"])
    
    return {
        "tax_year": tax_year,
        "filing_status": filing_status,
        "filing_state": filing_state,
        "pay_periods": pay_periods,
        "gross_income": gross_income,
        "salary": salary,
        "stcg": stcg,
        "dividends": dividends,
        "ltcg": ltcg,
        # ISO Stock Options
        "iso_shares": iso_shares,
        "iso_strike": iso_strike,
        "iso_fmv": iso_fmv,
        "iso_bargain_element": iso_bargain_element,
        "pretax_deductions_annual": pretax_deductions_annual,
        "health_annual": health_annual,
        "dental_annual": dental_annual,
        "vision_annual": vision_annual,
        # Individual contributions
        "trad_401k": trad_401k,
        "roth_401k": roth_401k,
        "after_tax_401k": after_tax_401k,
        "trad_ira": trad_ira,
        "roth_ira": roth_ira,
        "spousal_trad_ira": spousal_trad_ira,
        "spousal_roth_ira": spousal_roth_ira,
        "employer_401k": employer_401k,
        # Totals
        "pretax_retirement": pretax_retirement,
        "aftertax_retirement": aftertax_retirement,
        "employee_contributions": employee_contributions,
        "total_retirement_with_employer": total_retirement_with_employer,
        # AGI/Deductions
        "agi": agi,
        "magi": magi,
        "standard_deduction": standard_deduction,
        "deduction_used": deduction_used,
        "deduction_type": deduction_type,
        "itemized_deductions": itemized_deductions,
        "mortgage_interest": mortgage_interest,
        "property_taxes": property_taxes,
        "salt_capped": salt_capped,
        "charitable": charitable,
        "other_deductions": other_deductions,
        "student_loan_interest": student_loan_int,
        "above_the_line_deductions": above_the_line_deductions,
        "taxable_ordinary": taxable_ordinary,
        # Tax Credits
        "child_credit": child_credit,
        "education_credits": education_credits,
        "other_credits": other_credits,
        "total_credits": total_credits,
        "federal_tax_before_credits": federal_tax_before_credits,
        # Federal tax (regular)
        "regular_tax": regular_tax,
        "federal_tax_ordinary": federal_tax_ordinary,
        "ltcg_tax": ltcg_tax,
        # AMT
        "amti": amti,
        "amt_exemption": amt_result["exemption"],
        "amt_taxable": amt_result["amt_taxable"],
        "amt": amt_result["amt"],
        "amt_rate_26_amount": amt_result["rate_26_amount"],
        "amt_rate_28_amount": amt_result["rate_28_amount"],
        "tentative_minimum_tax": tentative_minimum_tax,
        "amt_applies": amt_applies,
        "amt_owed": amt_owed,
        # Total federal (higher of regular or AMT)
        "total_federal_tax": total_federal_tax,
        "federal_rate": federal_rate,
        "federal_brackets": federal_brackets,
        "federal_breakdown": federal_breakdown,
        # State tax
        "state_name": state_tax_result["state"],
        "state_code": state_tax_result["state_code"],
        "mo_standard_deduction": mo_standard_deduction,  # Backward compat
        "mo_taxable_income": mo_taxable_income,  # Backward compat
        "mo_state_tax": mo_state_tax,  # Backward compat
        "state_standard_deduction": state_standard_deduction,
        "state_taxable_income": state_taxable_income,
        "state_tax": state_tax,
        "state_rate": state_rate,
        "mo_brackets": state_brackets,  # Now uses state-specific brackets
        "mo_breakdown": mo_breakdown,  # Backward compat
        "state_brackets": state_brackets,
        "state_breakdown": state_breakdown,
        "mental_health_tax": mental_health_tax,
        "city_tax": city_tax,
        # FICA
        "social_security": fica["social_security"],
        "medicare": fica["medicare"],
        "additional_medicare": fica["additional_medicare"],
        "total_fica": fica["total_fica"],
        "fica_rate": fica_rate,
        "ss_wage_base": fica["ss_wage_base"],
        # Totals
        "total_taxes": total_taxes,
        "tax_rate": tax_rate,
        # Per paycheck
        "gross_per_pay": gross_per_pay,
        "federal_tax_per_pay": federal_tax_per_pay,
        "state_tax_per_pay": state_tax_per_pay,
        "fica_per_pay": fica_per_pay,
        "total_tax_per_pay": total_tax_per_pay,
        "pretax_deductions_per_pay": pretax_deductions_per_pay,
        "pretax_retirement_per_pay": pretax_retirement_per_pay,
        "aftertax_retirement_per_pay": aftertax_retirement_per_pay,
        "net_per_pay": net_per_pay,
    }


@router.get("/income-taxes")
def income_taxes_get(request: Request, db: Session = Depends(get_db), tax_year: int = None):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return RedirectResponse("/login")
    data = db.query(IncomeTaxes).filter(IncomeTaxes.user_id == user.id).first()
    
    # Use query param tax_year if provided, otherwise use saved or default to 2025
    selected_year = tax_year or (getattr(data, 'tax_year', None) if data else None) or 2025
    
    calculated = calculate_taxes(data, selected_year) if data else None
    profile_picture_b64, profile_picture_type = get_profile_picture_data(user)
    
    return templates.TemplateResponse("income_taxes.html", {
        "request": request,
        "title": "Income & Taxes",
        "user": user,
        "pay_frequencies": PAY_FREQUENCIES,
        "filing_statuses": FILING_STATUSES,
        "filing_states": FILING_STATES,
        "tax_years": TAX_YEARS,
        "selected_tax_year": selected_year,
        "contribs": CONTRIBS,
        "data": data,
        "calculated": calculated,
        "getattr": getattr,
        "float": float,
        "profile_picture_b64": profile_picture_b64,
        "profile_picture_type": profile_picture_type,
        "dark_mode": user.dark_mode
    })


@router.post("/income-taxes")
def income_taxes_post(
    request: Request,
    db: Session = Depends(get_db),
    tax_year: int = Form(2025),
    filing_status: str = Form("married_filing_jointly"),
    filing_state: str = Form("MO"),
    base_salary: float = Form(...),
    pay_frequency: str = Form(...),
    short_term_cap_gains: float = Form(0.0),
    dividends_interest: float = Form(0.0),
    long_term_cap_gains: float = Form(0.0),
    iso_shares_exercised: int = Form(0),
    iso_strike_price: float = Form(0.0),
    iso_fmv_at_exercise: float = Form(0.0),
    health_insurance_per_pay: float = Form(0.0),
    dental_per_pay: float = Form(0.0),
    vision_per_pay: float = Form(0.0),
    traditional_401k: float = Form(0.0),
    traditional_401k_type: str = Form("$"),
    roth_401k: float = Form(0.0),
    roth_401k_type: str = Form("$"),
    after_tax_401k: float = Form(0.0),
    after_tax_401k_type: str = Form("$"),
    traditional_ira: float = Form(0.0),
    traditional_ira_type: str = Form("$"),
    roth_ira: float = Form(0.0),
    roth_ira_type: str = Form("$"),
    spousal_ira: float = Form(0.0),
    spousal_ira_type: str = Form("$"),
    spousal_roth_ira: float = Form(0.0),
    spousal_roth_ira_type: str = Form("$"),
    employer_401k: float = Form(0.0),
    employer_401k_type: str = Form("$"),
    # Tax Credits
    child_tax_credit: float = Form(0.0),
    education_credits: float = Form(0.0),
    other_credits: float = Form(0.0),
    # Itemized Deductions
    mortgage_interest_deduction: float = Form(0.0),
    property_tax_deduction: float = Form(0.0),
    charitable_deduction: float = Form(0.0),
    student_loan_interest: float = Form(0.0),
    other_deductions: float = Form(0.0),
    use_itemized: bool = Form(False),
):
    username = request.cookies.get("username")
    if not username:
        return RedirectResponse("/login")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return RedirectResponse("/login")
    row = db.query(IncomeTaxes).filter(IncomeTaxes.user_id == user.id).first()
    if not row:
        row = IncomeTaxes(user_id=user.id)
        db.add(row)
    
    row.tax_year = tax_year
    row.filing_status = filing_status
    row.filing_state = filing_state
    row.base_salary = base_salary
    row.pay_frequency = pay_frequency
    row.short_term_cap_gains = short_term_cap_gains
    row.dividends_interest = dividends_interest
    row.long_term_cap_gains = long_term_cap_gains
    row.iso_shares_exercised = iso_shares_exercised
    row.iso_strike_price = iso_strike_price
    row.iso_fmv_at_exercise = iso_fmv_at_exercise
    row.health_insurance_per_pay = health_insurance_per_pay
    row.dental_per_pay = dental_per_pay
    row.vision_per_pay = vision_per_pay
    row.traditional_401k = traditional_401k
    row.traditional_401k_type = traditional_401k_type
    row.roth_401k = roth_401k
    row.roth_401k_type = roth_401k_type
    row.after_tax_401k = after_tax_401k
    row.after_tax_401k_type = after_tax_401k_type
    row.traditional_ira = traditional_ira
    row.traditional_ira_type = traditional_ira_type
    row.roth_ira = roth_ira
    row.roth_ira_type = roth_ira_type
    row.spousal_ira = spousal_ira
    row.spousal_ira_type = spousal_ira_type
    row.spousal_roth_ira = spousal_roth_ira
    row.spousal_roth_ira_type = spousal_roth_ira_type
    row.employer_401k = employer_401k
    row.employer_401k_type = employer_401k_type
    # Tax Credits
    row.child_tax_credit = child_tax_credit
    row.education_credits = education_credits
    row.other_credits = other_credits
    # Itemized Deductions
    row.mortgage_interest_deduction = mortgage_interest_deduction
    row.property_tax_deduction = property_tax_deduction
    row.charitable_deduction = charitable_deduction
    row.student_loan_interest = student_loan_interest
    row.other_deductions = other_deductions
    row.use_itemized = use_itemized
    db.commit()
    return RedirectResponse("/income-taxes", status_code=303)
