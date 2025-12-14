"""Add tracking_period_months to budget_items

Revision ID: bcb4694a6e46
Revises: 5c0699b6bbf1
Create Date: 2025-12-13 18:41:59.497525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcb4694a6e46'
down_revision: Union[str, Sequence[str], None] = '5c0699b6bbf1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add tracking_period_months to budget_items for variable expense averaging period selection
    with op.batch_alter_table('budget_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tracking_period_months', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('budget_items', schema=None) as batch_op:
        batch_op.drop_column('tracking_period_months')
