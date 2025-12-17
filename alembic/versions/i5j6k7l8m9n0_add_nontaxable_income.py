"""Add non-taxable income fields

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2024-12-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'i5j6k7l8m9n0'
down_revision = 'h4i5j6k7l8m9'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add non-taxable income columns to income_taxes table."""
    columns_to_add = [
        ('roth_ira_distribution', sa.Float(), True, '0'),
        ('roth_401k_distribution', sa.Float(), True, '0'),
        ('other_nontaxable_income', sa.Float(), True, '0'),
    ]
    
    for col_name, col_type, nullable, server_default in columns_to_add:
        if not column_exists('income_taxes', col_name):
            op.add_column('income_taxes', sa.Column(col_name, col_type, nullable=nullable, server_default=server_default))


def downgrade() -> None:
    """Remove non-taxable income columns."""
    columns_to_drop = [
        'other_nontaxable_income',
        'roth_401k_distribution',
        'roth_ira_distribution',
    ]
    
    for col_name in columns_to_drop:
        if column_exists('income_taxes', col_name):
            op.drop_column('income_taxes', col_name)
