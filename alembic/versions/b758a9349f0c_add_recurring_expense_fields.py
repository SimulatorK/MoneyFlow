"""add_recurring_expense_fields

Revision ID: b758a9349f0c
Revises: c7270b46308a
Create Date: 2025-12-13 21:09:09.643559

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b758a9349f0c'
down_revision: Union[str, Sequence[str], None] = 'c7270b46308a'
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
    """Add recurring expense fields to expenses table."""
    if table_exists('expenses'):
        if not column_exists('expenses', 'is_recurring'):
            with op.batch_alter_table('expenses', schema=None) as batch_op:
                batch_op.add_column(sa.Column('is_recurring', sa.String(length=10), nullable=True))
        
        if not column_exists('expenses', 'frequency'):
            with op.batch_alter_table('expenses', schema=None) as batch_op:
                batch_op.add_column(sa.Column('frequency', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Remove recurring expense fields."""
    if table_exists('expenses'):
        for col_name in ['frequency', 'is_recurring']:
            if column_exists('expenses', col_name):
                with op.batch_alter_table('expenses', schema=None) as batch_op:
                    batch_op.drop_column(col_name)
