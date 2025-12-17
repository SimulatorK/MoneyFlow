"""Add net worth tables

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2025-12-14 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Create net worth tracking tables."""
    # Create accounts table if not exists
    if not table_exists('networth_accounts'):
        op.create_table(
            'networth_accounts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('account_type', sa.String(length=50), nullable=False),
            sa.Column('is_asset', sa.Boolean(), nullable=False, default=True),
            sa.Column('institution', sa.String(length=255), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
            sa.Column('use_for_fire', sa.Boolean(), nullable=True, default=True),  # Include from start
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_networth_accounts_user_id'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_networth_accounts_id'), 'networth_accounts', ['id'], unique=False)
    
    # Create balances table if not exists
    if not table_exists('networth_balances'):
        op.create_table(
            'networth_balances',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('account_id', sa.Integer(), nullable=False),
            sa.Column('balance_date', sa.Date(), nullable=False),
            sa.Column('balance', sa.Float(), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['account_id'], ['networth_accounts.id'], name='fk_networth_balances_account_id'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_networth_balances_id'), 'networth_balances', ['id'], unique=False)
    
    # Create contributions table if not exists
    if not table_exists('networth_contributions'):
        op.create_table(
            'networth_contributions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('account_id', sa.Integer(), nullable=False),
            sa.Column('amount', sa.Float(), nullable=True, default=0),
            sa.Column('frequency', sa.String(length=20), nullable=True, default='monthly'),
            sa.Column('employer_match', sa.Float(), nullable=True, default=0),
            sa.Column('employer_match_type', sa.String(length=10), nullable=True, default='percent'),
            sa.Column('employer_match_limit', sa.Float(), nullable=True, default=0),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['account_id'], ['networth_accounts.id'], name='fk_networth_contributions_account_id'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('account_id', name='uq_networth_contributions_account_id')
        )
        op.create_index(op.f('ix_networth_contributions_id'), 'networth_contributions', ['id'], unique=False)


def downgrade() -> None:
    """Drop net worth tracking tables."""
    if table_exists('networth_contributions'):
        op.drop_index(op.f('ix_networth_contributions_id'), table_name='networth_contributions')
        op.drop_table('networth_contributions')
    if table_exists('networth_balances'):
        op.drop_index(op.f('ix_networth_balances_id'), table_name='networth_balances')
        op.drop_table('networth_balances')
    if table_exists('networth_accounts'):
        op.drop_index(op.f('ix_networth_accounts_id'), table_name='networth_accounts')
        op.drop_table('networth_accounts')
