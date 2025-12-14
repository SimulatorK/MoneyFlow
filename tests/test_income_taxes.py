"""
Tests for income and tax calculation functionality.

Tests tax bracket calculations, deductions, and multi-year support.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.income_taxes import IncomeTaxes
from app.routes.income_taxes import (
    calculate_taxes,
    calculate_federal_tax_with_breakdown,
    calculate_missouri_tax_with_breakdown,
    calculate_fica,
    calculate_amt,
    get_tax_year_data,
    TAX_DATA
)


class TestTaxYearData:
    """Test suite for multi-year tax data."""
    
    def test_tax_data_exists_for_all_years(self):
        """Test that tax data exists for supported years."""
        supported_years = [2023, 2024, 2025, 2026]
        for year in supported_years:
            assert year in TAX_DATA
            data = TAX_DATA[year]
            assert "federal_brackets" in data
            assert "standard_deductions" in data
            assert "ltcg_brackets" in data
            assert "ss_wage_base" in data
    
    def test_get_tax_year_data_returns_correct_year(self):
        """Test that correct year data is returned."""
        data_2024 = get_tax_year_data(2024)
        data_2025 = get_tax_year_data(2025)
        
        # SS wage bases should differ by year
        assert data_2024["ss_wage_base"] != data_2025["ss_wage_base"]
    
    def test_get_tax_year_data_defaults_to_2025(self):
        """Test that invalid year defaults to 2025."""
        data = get_tax_year_data(1999)  # Invalid year
        assert data == TAX_DATA[2025]


class TestFederalTaxCalculation:
    """Test suite for federal tax calculations."""
    
    def test_federal_tax_zero_income(self):
        """Test federal tax is zero for zero income."""
        tax, breakdown = calculate_federal_tax_with_breakdown(0, "single", 2025)
        assert tax == 0
    
    def test_federal_tax_single_filer(self):
        """Test federal tax calculation for single filer."""
        # Test with $50,000 taxable income
        tax, breakdown = calculate_federal_tax_with_breakdown(50000, "single", 2025)
        
        # Tax should be positive
        assert tax > 0
        
        # Breakdown should have entries
        assert len(breakdown) > 0
    
    def test_federal_tax_married_joint(self):
        """Test that married filing jointly has lower taxes at same income."""
        income = 100000
        
        single_tax, _ = calculate_federal_tax_with_breakdown(income, "single", 2025)
        married_tax, _ = calculate_federal_tax_with_breakdown(income, "married_filing_jointly", 2025)
        
        # Married filing jointly should have lower tax due to wider brackets
        assert married_tax < single_tax
    
    def test_federal_tax_progressive_brackets(self):
        """Test that tax increases with income but at diminishing rate."""
        tax_50k, _ = calculate_federal_tax_with_breakdown(50000, "single", 2025)
        tax_100k, _ = calculate_federal_tax_with_breakdown(100000, "single", 2025)
        tax_200k, _ = calculate_federal_tax_with_breakdown(200000, "single", 2025)
        
        # Each should be progressively higher
        assert tax_100k > tax_50k
        assert tax_200k > tax_100k
        
        # But effective rate should increase
        rate_50k = tax_50k / 50000
        rate_100k = tax_100k / 100000
        rate_200k = tax_200k / 200000
        
        assert rate_100k > rate_50k
        assert rate_200k > rate_100k


class TestMissouriTaxCalculation:
    """Test suite for Missouri state tax calculations."""
    
    def test_mo_tax_zero_income(self):
        """Test Missouri tax is zero for zero income."""
        tax, breakdown = calculate_missouri_tax_with_breakdown(0, 2025)
        assert tax == 0
    
    def test_mo_tax_positive_income(self):
        """Test Missouri tax calculation for positive income."""
        tax, breakdown = calculate_missouri_tax_with_breakdown(50000, 2025)
        
        assert tax > 0
        assert len(breakdown) > 0
    
    def test_mo_tax_rate_cap(self):
        """Test that Missouri has a maximum marginal rate around 4.8%."""
        # High income should hit the max bracket
        tax, breakdown = calculate_missouri_tax_with_breakdown(500000, 2025)
        
        # Effective rate should be less than max marginal rate
        effective_rate = tax / 500000
        assert effective_rate < 0.05  # Less than 5%


class TestFICACalculation:
    """Test suite for FICA tax calculations."""
    
    def test_fica_basic_calculation(self):
        """Test basic FICA calculation."""
        fica = calculate_fica(60000, "single", 2025)
        
        assert "social_security" in fica
        assert "medicare" in fica
        assert "total_fica" in fica
        
        # SS should be 6.2% up to wage base
        assert fica["social_security"] == 60000 * 0.062
        
        # Medicare should be 1.45%
        assert fica["medicare"] == 60000 * 0.0145
    
    def test_fica_ss_wage_cap(self):
        """Test Social Security wage base cap."""
        year_data = get_tax_year_data(2025)
        wage_base = year_data["ss_wage_base"]
        
        # Income above wage base
        high_income = wage_base + 50000
        fica = calculate_fica(high_income, "single", 2025)
        
        # SS should be capped at wage base
        assert fica["social_security"] == wage_base * 0.062
    
    def test_fica_additional_medicare(self):
        """Test additional Medicare tax for high earners."""
        # Single filers pay additional 0.9% over $200k
        fica = calculate_fica(300000, "single", 2025)
        
        assert fica["additional_medicare"] > 0
        assert fica["additional_medicare"] == (300000 - 200000) * 0.009


class TestAMTCalculation:
    """Test suite for Alternative Minimum Tax calculations."""
    
    def test_amt_below_exemption(self):
        """Test AMT is zero when below exemption."""
        # Low AMTI should result in no AMT
        amt_result = calculate_amt(50000, "single", 2025)
        
        assert amt_result["amt"] == 0
        assert amt_result["exemption"] > 0
    
    def test_amt_above_exemption(self):
        """Test AMT calculation above exemption threshold."""
        # High AMTI should result in AMT
        amt_result = calculate_amt(500000, "single", 2025)
        
        assert amt_result["amt"] > 0
        assert amt_result["amt_taxable"] > 0


class TestFullTaxCalculation:
    """Test suite for complete tax calculation."""
    
    def test_calculate_taxes_with_valid_data(
        self,
        db_session: Session,
        test_income_taxes: IncomeTaxes
    ):
        """Test full tax calculation with valid income data."""
        result = calculate_taxes(test_income_taxes)
        
        assert result is not None
        assert "total_taxes" in result
        assert "total_federal_tax" in result
        assert "mo_state_tax" in result
        assert "total_fica" in result
        assert "net_per_pay" in result
    
    def test_calculate_taxes_returns_none_for_empty_data(self):
        """Test that None is returned for missing income data."""
        result = calculate_taxes(None)
        assert result is None
    
    def test_calculate_taxes_different_years(
        self,
        db_session: Session,
        test_income_taxes: IncomeTaxes
    ):
        """Test that different tax years produce different results."""
        result_2024 = calculate_taxes(test_income_taxes, tax_year=2024)
        result_2025 = calculate_taxes(test_income_taxes, tax_year=2025)
        
        # Standard deductions differ by year
        assert result_2024["standard_deduction"] != result_2025["standard_deduction"]


class TestIncomeTaxesPage:
    """Test suite for income and taxes page."""
    
    def test_income_taxes_page_loads(
        self,
        client: TestClient,
        test_user_with_auth: User
    ):
        """Test that income taxes page loads successfully."""
        response = client.get("/income-taxes")
        assert response.status_code == 200
        assert "Income" in response.text or "Tax" in response.text
    
    def test_income_taxes_page_shows_year_selector(
        self,
        client: TestClient,
        test_user_with_auth: User
    ):
        """Test that tax year selector is present."""
        response = client.get("/income-taxes")
        assert response.status_code == 200
        # Should have year options
        assert "2024" in response.text or "2025" in response.text
    
    def test_income_taxes_save(
        self,
        client: TestClient,
        db_session: Session,
        test_user_with_auth: User
    ):
        """Test saving income tax data."""
        response = client.post(
            "/income-taxes",
            data={
                "tax_year": 2025,
                "filing_status": "single",
                "filing_state": "MO",
                "base_salary": 75000,
                "pay_frequency": "bi-weekly"
            },
            follow_redirects=False
        )
        assert response.status_code in [302, 303, 307]
        
        # Verify data was saved
        income = db_session.query(IncomeTaxes).filter(
            IncomeTaxes.base_salary == 75000
        ).first()
        assert income is not None
        assert income.tax_year == 2025
