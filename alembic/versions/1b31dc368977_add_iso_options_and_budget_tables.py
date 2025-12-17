"""add_iso_options_and_budget_tables

Revision ID: 1b31dc368977
Revises: 2dade53f88fc
Create Date: 2025-12-13 15:53:08.389992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '1b31dc368977'
down_revision: Union[str, Sequence[str], None] = '2dade53f88fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema."""
    # Add ISO columns only if they don't exist
    columns_to_add = [
        ('iso_shares_exercised', sa.Integer(), True),
        ('iso_strike_price', sa.Float(), True),
        ('iso_fmv_at_exercise', sa.Float(), True),
    ]
    
    for col_name, col_type, nullable in columns_to_add:
        if not column_exists('income_taxes', col_name):
            with op.batch_alter_table('income_taxes', schema=None) as batch_op:
                batch_op.add_column(sa.Column(col_name, col_type, nullable=nullable))


def downgrade() -> None:
    """Downgrade schema."""
    columns_to_drop = ['iso_fmv_at_exercise', 'iso_strike_price', 'iso_shares_exercised']
    
    for col_name in columns_to_drop:
        if column_exists('income_taxes', col_name):
            with op.batch_alter_table('income_taxes', schema=None) as batch_op:
                batch_op.drop_column(col_name)
