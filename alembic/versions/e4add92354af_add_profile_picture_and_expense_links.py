"""add_profile_picture_and_expense_links

Revision ID: e4add92354af
Revises: 24987ef4ea7c
Create Date: 2025-12-13 18:07:29.589116

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e4add92354af'
down_revision: Union[str, Sequence[str], None] = '24987ef4ea7c'
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
    """Upgrade schema."""
    # Add columns to fixed_costs if table exists
    if table_exists('fixed_costs'):
        if not column_exists('fixed_costs', 'expense_category_id'):
            with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
                batch_op.add_column(sa.Column('expense_category_id', sa.Integer(), nullable=True))
        
        if not column_exists('fixed_costs', 'expense_subcategory_id'):
            with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
                batch_op.add_column(sa.Column('expense_subcategory_id', sa.Integer(), nullable=True))

    # Add columns to users
    if table_exists('users'):
        columns_to_add = [
            ('profile_picture', sa.LargeBinary(), True),
            ('profile_picture_type', sa.String(), True),
            ('updated_at', sa.DateTime(), True),
        ]
        
        for col_name, col_type, nullable in columns_to_add:
            if not column_exists('users', col_name):
                with op.batch_alter_table('users', schema=None) as batch_op:
                    batch_op.add_column(sa.Column(col_name, col_type, nullable=nullable))


def downgrade() -> None:
    """Downgrade schema."""
    if table_exists('users'):
        for col_name in ['updated_at', 'profile_picture_type', 'profile_picture']:
            if column_exists('users', col_name):
                with op.batch_alter_table('users', schema=None) as batch_op:
                    batch_op.drop_column(col_name)

    if table_exists('fixed_costs'):
        for col_name in ['expense_subcategory_id', 'expense_category_id']:
            if column_exists('fixed_costs', col_name):
                with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
                    batch_op.drop_column(col_name)
