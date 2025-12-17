"""Add tutorial fields to users

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
Create Date: 2025-12-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'g3h4i5j6k7l8'
down_revision: Union[str, None] = 'f2g3h4i5j6k7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add tutorial_completed and tutorial_step fields to users table."""
    # Only add columns if they don't already exist (for fresh databases where initial migration includes them)
    if not column_exists('users', 'tutorial_completed'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('tutorial_completed', sa.Boolean(), nullable=True, default=False))
    
    if not column_exists('users', 'tutorial_step'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('tutorial_step', sa.Integer(), nullable=True, default=0))


def downgrade() -> None:
    """Remove tutorial fields from users table."""
    if column_exists('users', 'tutorial_step'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.drop_column('tutorial_step')
    
    if column_exists('users', 'tutorial_completed'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.drop_column('tutorial_completed')
