"""Add non-taxable income fields

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2024-12-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i5j6k7l8m9n0'
down_revision = 'h4i5j6k7l8m9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add non-taxable income columns to income_taxes table
    op.add_column('income_taxes', sa.Column('roth_ira_distribution', sa.Float(), nullable=True, server_default='0'))
    op.add_column('income_taxes', sa.Column('roth_401k_distribution', sa.Float(), nullable=True, server_default='0'))
    op.add_column('income_taxes', sa.Column('other_nontaxable_income', sa.Float(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('income_taxes', 'other_nontaxable_income')
    op.drop_column('income_taxes', 'roth_401k_distribution')
    op.drop_column('income_taxes', 'roth_ira_distribution')

