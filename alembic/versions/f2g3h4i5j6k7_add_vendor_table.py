"""Add vendor table and vendor_id to expenses

Revision ID: f2g3h4i5j6k7
Revises: e5f6g7h8i9j0
Create Date: 2025-12-15 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f2g3h4i5j6k7'
down_revision: Union[str, None] = 'e5f6g7h8i9j0'
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
    """Create vendors table and add vendor_id to expenses."""
    # Create vendors table if it doesn't exist
    if not table_exists('vendors'):
        op.create_table(
            'vendors',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_vendors_user_id'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_vendors_id'), 'vendors', ['id'], unique=False)
    
    # Add vendor_id column to expenses table if it doesn't exist
    if table_exists('expenses') and not column_exists('expenses', 'vendor_id'):
        with op.batch_alter_table('expenses', schema=None) as batch_op:
            batch_op.add_column(sa.Column('vendor_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_expenses_vendor_id', 'vendors', ['vendor_id'], ['id'])


def downgrade() -> None:
    """Remove vendor_id from expenses and drop vendors table."""
    if column_exists('expenses', 'vendor_id'):
        with op.batch_alter_table('expenses', schema=None) as batch_op:
            batch_op.drop_constraint('fk_expenses_vendor_id', type_='foreignkey')
            batch_op.drop_column('vendor_id')
    
    if table_exists('vendors'):
        op.drop_index(op.f('ix_vendors_id'), table_name='vendors')
        op.drop_table('vendors')
