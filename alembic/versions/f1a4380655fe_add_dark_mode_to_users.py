"""Add dark_mode to users

Revision ID: f1a4380655fe
Revises: bcb4694a6e46
Create Date: 2025-12-13 20:31:17.335830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f1a4380655fe'
down_revision: Union[str, Sequence[str], None] = 'bcb4694a6e46'
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
    if not column_exists('users', 'dark_mode'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('dark_mode', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if column_exists('users', 'dark_mode'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.drop_column('dark_mode')
