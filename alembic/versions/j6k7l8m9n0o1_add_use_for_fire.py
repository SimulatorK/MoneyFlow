"""Add use_for_fire column to accounts

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j6k7l8m9n0o1'
down_revision = 'i5j6k7l8m9n0'
branch_labels = None
depends_on = None


def upgrade():
    # Add use_for_fire column to networth_accounts table
    op.add_column('networth_accounts', sa.Column('use_for_fire', sa.Boolean(), nullable=True))
    
    # Set default value for existing rows
    op.execute("UPDATE networth_accounts SET use_for_fire = 1")


def downgrade():
    op.drop_column('networth_accounts', 'use_for_fire')

