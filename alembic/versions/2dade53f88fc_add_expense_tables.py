"""add_expense_tables

Revision ID: 2dade53f88fc
Revises: edd43dfbe2d8
Create Date: 2025-12-13 15:13:48.296079

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '2dade53f88fc'
down_revision: Union[str, Sequence[str], None] = 'edd43dfbe2d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    # Create categories table if not exists
    if not table_exists('categories'):
        op.create_table('categories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('categories', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_categories_id'), ['id'], unique=False)

    # Create subcategories table if not exists
    if not table_exists('subcategories'):
        op.create_table('subcategories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('category_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('subcategories', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_subcategories_id'), ['id'], unique=False)

    # Create expenses table if not exists
    if not table_exists('expenses'):
        op.create_table('expenses',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('category_id', sa.Integer(), nullable=False),
            sa.Column('subcategory_id', sa.Integer(), nullable=True),
            sa.Column('amount', sa.Float(), nullable=False),
            sa.Column('expense_date', sa.Date(), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
            sa.ForeignKeyConstraint(['subcategory_id'], ['subcategories.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('expenses', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_expenses_id'), ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    if table_exists('expenses'):
        with op.batch_alter_table('expenses', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_expenses_id'))
        op.drop_table('expenses')
    
    if table_exists('subcategories'):
        with op.batch_alter_table('subcategories', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_subcategories_id'))
        op.drop_table('subcategories')
    
    if table_exists('categories'):
        with op.batch_alter_table('categories', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_categories_id'))
        op.drop_table('categories')
