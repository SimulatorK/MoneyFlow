"""Initial migration with users and income_taxes tables

Revision ID: 07af927ecd81
Revises: 
Create Date: 2025-12-13 14:44:56.121639

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07af927ecd81'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create users and income_taxes tables."""
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('username', sa.String(), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('profile_picture', sa.LargeBinary(), nullable=True),
        sa.Column('profile_picture_type', sa.String(), nullable=True),
        sa.Column('dark_mode', sa.Boolean(), default=False),
        sa.Column('tutorial_completed', sa.Boolean(), default=False),
        sa.Column('tutorial_step', sa.Integer(), default=0),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    
    # Create income_taxes table
    op.create_table(
        'income_taxes',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), unique=True, nullable=False),
        sa.Column('tax_year', sa.Integer(), default=2025),
        sa.Column('filing_status', sa.String(), default='married_filing_jointly'),
        sa.Column('filing_state', sa.String(), default='MO'),
        sa.Column('base_salary', sa.Float(), default=0),
        sa.Column('pay_frequency', sa.String(), nullable=True),
        # Non-employment income
        sa.Column('social_security_income', sa.Float(), default=0),
        sa.Column('pension_income', sa.Float(), default=0),
        sa.Column('traditional_ira_distribution', sa.Float(), default=0),
        sa.Column('traditional_401k_distribution', sa.Float(), default=0),
        sa.Column('other_taxable_income', sa.Float(), default=0),
        # Non-taxable income
        sa.Column('roth_ira_distribution', sa.Float(), default=0),
        sa.Column('roth_401k_distribution', sa.Float(), default=0),
        sa.Column('other_nontaxable_income', sa.Float(), default=0),
        # Investment income
        sa.Column('short_term_cap_gains', sa.Float(), default=0),
        sa.Column('dividends_interest', sa.Float(), default=0),
        sa.Column('long_term_cap_gains', sa.Float(), default=0),
        # ISO Stock Options
        sa.Column('iso_shares_exercised', sa.Integer(), default=0),
        sa.Column('iso_strike_price', sa.Float(), default=0),
        sa.Column('iso_fmv_at_exercise', sa.Float(), default=0),
        # Pretax deductions
        sa.Column('health_insurance_per_pay', sa.Float(), default=0),
        sa.Column('dental_per_pay', sa.Float(), default=0),
        sa.Column('vision_per_pay', sa.Float(), default=0),
        # Retirement contributions
        sa.Column('traditional_401k', sa.Float(), nullable=True),
        sa.Column('traditional_401k_type', sa.String(), nullable=True),
        sa.Column('roth_401k', sa.Float(), nullable=True),
        sa.Column('roth_401k_type', sa.String(), nullable=True),
        sa.Column('after_tax_401k', sa.Float(), nullable=True),
        sa.Column('after_tax_401k_type', sa.String(), nullable=True),
        sa.Column('traditional_ira', sa.Float(), nullable=True),
        sa.Column('traditional_ira_type', sa.String(), nullable=True),
        sa.Column('roth_ira', sa.Float(), nullable=True),
        sa.Column('roth_ira_type', sa.String(), nullable=True),
        sa.Column('spousal_ira', sa.Float(), nullable=True),
        sa.Column('spousal_ira_type', sa.String(), nullable=True),
        sa.Column('spousal_roth_ira', sa.Float(), nullable=True),
        sa.Column('spousal_roth_ira_type', sa.String(), nullable=True),
        sa.Column('employer_401k', sa.Float(), nullable=True),
        sa.Column('employer_401k_type', sa.String(), nullable=True),
        # Tax Credits
        sa.Column('child_tax_credit', sa.Float(), default=0),
        sa.Column('education_credits', sa.Float(), default=0),
        sa.Column('other_credits', sa.Float(), default=0),
        # Itemized Deductions
        sa.Column('mortgage_interest_deduction', sa.Float(), default=0),
        sa.Column('property_tax_deduction', sa.Float(), default=0),
        sa.Column('charitable_deduction', sa.Float(), default=0),
        sa.Column('student_loan_interest', sa.Float(), default=0),
        sa.Column('other_deductions', sa.Float(), default=0),
        sa.Column('use_itemized', sa.Boolean(), default=False),
    )


def downgrade() -> None:
    """Downgrade schema - Drop tables."""
    op.drop_table('income_taxes')
    op.drop_table('users')
