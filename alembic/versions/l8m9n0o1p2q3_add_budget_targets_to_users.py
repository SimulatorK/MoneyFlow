"""Add budget targets to users

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0o1p2
Create Date: 2024-12-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l8m9n0o1p2q3'
down_revision: Union[str, None] = 'k7l8m9n0o1p2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add budget target columns with defaults
    op.add_column('users', sa.Column('budget_needs_target', sa.Float(), nullable=True, server_default='50.0'))
    op.add_column('users', sa.Column('budget_wants_target', sa.Float(), nullable=True, server_default='30.0'))
    op.add_column('users', sa.Column('budget_savings_target', sa.Float(), nullable=True, server_default='20.0'))


def downgrade() -> None:
    op.drop_column('users', 'budget_savings_target')
    op.drop_column('users', 'budget_wants_target')
    op.drop_column('users', 'budget_needs_target')

