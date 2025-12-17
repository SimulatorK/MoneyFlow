"""Add use_for_fire column to accounts

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'j6k7l8m9n0o1'
down_revision = 'i5j6k7l8m9n0'
branch_labels = None
depends_on = None


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


def upgrade():
    # Only add if table exists and column doesn't
    if table_exists('networth_accounts') and not column_exists('networth_accounts', 'use_for_fire'):
        op.add_column('networth_accounts', sa.Column('use_for_fire', sa.Boolean(), nullable=True))
        # Set default value for existing rows
        op.execute("UPDATE networth_accounts SET use_for_fire = 1")


def downgrade():
    if column_exists('networth_accounts', 'use_for_fire'):
        op.drop_column('networth_accounts', 'use_for_fire')
