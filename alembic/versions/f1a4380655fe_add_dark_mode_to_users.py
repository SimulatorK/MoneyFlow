"""Add dark_mode to users

Revision ID: f1a4380655fe
Revises: bcb4694a6e46
Create Date: 2025-12-13 20:31:17.335830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a4380655fe'
down_revision: Union[str, Sequence[str], None] = 'bcb4694a6e46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dark_mode', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('dark_mode')
