"""Add tutorial fields to users

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
Create Date: 2025-12-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g3h4i5j6k7l8'
down_revision: Union[str, None] = 'f2g3h4i5j6k7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tutorial_completed and tutorial_step fields to users table."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tutorial_completed', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('tutorial_step', sa.Integer(), nullable=True, default=0))


def downgrade() -> None:
    """Remove tutorial fields from users table."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('tutorial_step')
        batch_op.drop_column('tutorial_completed')

