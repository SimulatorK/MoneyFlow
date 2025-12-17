"""Add tracking_period_months to budget_items

Revision ID: bcb4694a6e46
Revises: 5c0699b6bbf1
Create Date: 2025-12-13 18:41:59.497525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'bcb4694a6e46'
down_revision: Union[str, Sequence[str], None] = '5c0699b6bbf1'
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
    # Add tracking_period_months to budget_items for variable expense averaging period selection
    if table_exists('budget_items') and not column_exists('budget_items', 'tracking_period_months'):
        with op.batch_alter_table('budget_items', schema=None) as batch_op:
            batch_op.add_column(sa.Column('tracking_period_months', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if table_exists('budget_items') and column_exists('budget_items', 'tracking_period_months'):
        with op.batch_alter_table('budget_items', schema=None) as batch_op:
            batch_op.drop_column('tracking_period_months')
