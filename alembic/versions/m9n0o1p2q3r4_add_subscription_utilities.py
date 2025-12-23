"""Add subscription utilities tables

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
Create Date: 2024-12-23 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm9n0o1p2q3r4'
down_revision: Union[str, None] = 'l8m9n0o1p2q3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create subscription_utilities table
    op.create_table(
        'subscription_utilities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('utility_type', sa.String(50), nullable=True, server_default='subscription'),
        sa.Column('category_type', sa.String(50), nullable=True, server_default='need'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('notes', sa.String(500), nullable=True),
        sa.Column('expense_category_id', sa.Integer(), nullable=True),
        sa.Column('expense_subcategory_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['expense_category_id'], ['categories.id']),
        sa.ForeignKeyConstraint(['expense_subcategory_id'], ['subcategories.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscription_utilities_id'), 'subscription_utilities', ['id'], unique=False)
    
    # Create subscription_payments table
    op.create_table(
        'subscription_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('notes', sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscription_utilities.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscription_payments_id'), 'subscription_payments', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_subscription_payments_id'), table_name='subscription_payments')
    op.drop_table('subscription_payments')
    op.drop_index(op.f('ix_subscription_utilities_id'), table_name='subscription_utilities')
    op.drop_table('subscription_utilities')

