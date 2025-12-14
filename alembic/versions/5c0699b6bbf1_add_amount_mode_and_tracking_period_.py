"""Add amount_mode and tracking_period_months to fixed_costs

Revision ID: 5c0699b6bbf1
Revises: e4add92354af
Create Date: 2025-12-13 18:25:01.821003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c0699b6bbf1'
down_revision: Union[str, Sequence[str], None] = 'e4add92354af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns for amount mode selection
    with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('amount_mode', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('tracking_period_months', sa.Integer(), nullable=True))
    
    # Note: Foreign keys for expense_category_id and expense_subcategory_id 
    # were already added in previous migration. Skip if they exist.


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
        batch_op.drop_column('tracking_period_months')
        batch_op.drop_column('amount_mode')
