"""add_budget_tables

Revision ID: 24987ef4ea7c
Revises: 1b31dc368977
Create Date: 2025-12-13 15:54:19.110054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24987ef4ea7c'
down_revision: Union[str, Sequence[str], None] = '1b31dc368977'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create budget_categories table
    op.create_table(
        'budget_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('category_type', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_budget_categories_id'), 'budget_categories', ['id'], unique=False)
    
    # Create fixed_costs table
    op.create_table(
        'fixed_costs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('frequency', sa.String(length=50), nullable=True),
        sa.Column('category_type', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['budget_categories.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fixed_costs_id'), 'fixed_costs', ['id'], unique=False)
    
    # Create budget_items table
    op.create_table(
        'budget_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('budget_category_id', sa.Integer(), nullable=True),
        sa.Column('expense_category_id', sa.Integer(), nullable=True),
        sa.Column('expense_subcategory_id', sa.Integer(), nullable=True),
        sa.Column('use_tracked_average', sa.Boolean(), nullable=True),
        sa.Column('specified_amount', sa.Float(), nullable=True),
        sa.Column('category_type', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['budget_category_id'], ['budget_categories.id'], ),
        sa.ForeignKeyConstraint(['expense_category_id'], ['categories.id'], ),
        sa.ForeignKeyConstraint(['expense_subcategory_id'], ['subcategories.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_budget_items_id'), 'budget_items', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_budget_items_id'), table_name='budget_items')
    op.drop_table('budget_items')
    op.drop_index(op.f('ix_fixed_costs_id'), table_name='fixed_costs')
    op.drop_table('fixed_costs')
    op.drop_index(op.f('ix_budget_categories_id'), table_name='budget_categories')
    op.drop_table('budget_categories')
