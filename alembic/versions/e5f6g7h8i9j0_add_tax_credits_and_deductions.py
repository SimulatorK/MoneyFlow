"""Add tax credits and deductions to income_taxes

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2025-12-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add tax credits and deductions columns to income_taxes table."""
    columns_to_add = [
        # Tax Credits
        ('child_tax_credit', sa.Float(), True, '0'),
        ('education_credits', sa.Float(), True, '0'),
        ('other_credits', sa.Float(), True, '0'),
        # Additional Itemized Deductions
        ('mortgage_interest_deduction', sa.Float(), True, '0'),
        ('property_tax_deduction', sa.Float(), True, '0'),
        ('charitable_deduction', sa.Float(), True, '0'),
        ('student_loan_interest', sa.Float(), True, '0'),
        ('other_deductions', sa.Float(), True, '0'),
        ('use_itemized', sa.Boolean(), True, '0'),
    ]
    
    for col_name, col_type, nullable, server_default in columns_to_add:
        if not column_exists('income_taxes', col_name):
            with op.batch_alter_table('income_taxes', schema=None) as batch_op:
                batch_op.add_column(sa.Column(col_name, col_type, nullable=nullable, server_default=server_default))


def downgrade() -> None:
    """Remove tax credits and deductions columns from income_taxes table."""
    columns_to_drop = [
        'use_itemized', 'other_deductions', 'student_loan_interest',
        'charitable_deduction', 'property_tax_deduction', 'mortgage_interest_deduction',
        'other_credits', 'education_credits', 'child_tax_credit'
    ]
    
    for col_name in columns_to_drop:
        if column_exists('income_taxes', col_name):
            with op.batch_alter_table('income_taxes', schema=None) as batch_op:
                batch_op.drop_column(col_name)
