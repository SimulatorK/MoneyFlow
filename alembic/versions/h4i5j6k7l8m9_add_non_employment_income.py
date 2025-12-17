"""Add non-employment income fields to income_taxes

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2025-12-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'h4i5j6k7l8m9'
down_revision: Union[str, None] = 'g3h4i5j6k7l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add non-employment income fields to income_taxes table."""
    # Only add columns if they don't already exist
    columns_to_add = [
        ('social_security_income', sa.Float(), True, 0),
        ('pension_income', sa.Float(), True, 0),
        ('traditional_ira_distribution', sa.Float(), True, 0),
        ('traditional_401k_distribution', sa.Float(), True, 0),
        ('other_taxable_income', sa.Float(), True, 0),
    ]
    
    for col_name, col_type, nullable, default in columns_to_add:
        if not column_exists('income_taxes', col_name):
            op.add_column('income_taxes', sa.Column(col_name, col_type, nullable=nullable, default=default))


def downgrade() -> None:
    """Remove non-employment income fields from income_taxes table."""
    columns_to_drop = [
        'other_taxable_income',
        'traditional_401k_distribution',
        'traditional_ira_distribution',
        'pension_income',
        'social_security_income',
    ]
    
    for col_name in columns_to_drop:
        if column_exists('income_taxes', col_name):
            op.drop_column('income_taxes', col_name)
