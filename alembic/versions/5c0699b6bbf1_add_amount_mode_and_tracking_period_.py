"""Add amount_mode and tracking_period_months to fixed_costs

Revision ID: 5c0699b6bbf1
Revises: e4add92354af
Create Date: 2025-12-13 18:25:01.821003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '5c0699b6bbf1'
down_revision: Union[str, Sequence[str], None] = 'e4add92354af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns for amount mode selection if table exists
    if table_exists('fixed_costs'):
        if not column_exists('fixed_costs', 'amount_mode'):
            with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
                batch_op.add_column(sa.Column('amount_mode', sa.String(length=20), nullable=True))
        
        if not column_exists('fixed_costs', 'tracking_period_months'):
            with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
                batch_op.add_column(sa.Column('tracking_period_months', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if table_exists('fixed_costs'):
        for col_name in ['tracking_period_months', 'amount_mode']:
            if column_exists('fixed_costs', col_name):
                with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
                    batch_op.drop_column(col_name)
