"""add_recurring_expense_fields

Revision ID: b758a9349f0c
Revises: c7270b46308a
Create Date: 2025-12-13 21:09:09.643559

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b758a9349f0c'
down_revision: Union[str, Sequence[str], None] = 'c7270b46308a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add recurring expense fields to expenses table."""
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_recurring', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('frequency', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Remove recurring expense fields."""
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_column('frequency')
        batch_op.drop_column('is_recurring')
