"""Add non-employment income fields to income_taxes

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2025-12-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h4i5j6k7l8m9'
down_revision: Union[str, None] = 'g3h4i5j6k7l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add non-employment income fields to income_taxes table."""
    # Non-employment income fields
    op.add_column('income_taxes', sa.Column('social_security_income', sa.Float(), nullable=True, default=0))
    op.add_column('income_taxes', sa.Column('pension_income', sa.Float(), nullable=True, default=0))
    op.add_column('income_taxes', sa.Column('traditional_ira_distribution', sa.Float(), nullable=True, default=0))
    op.add_column('income_taxes', sa.Column('traditional_401k_distribution', sa.Float(), nullable=True, default=0))
    op.add_column('income_taxes', sa.Column('other_taxable_income', sa.Float(), nullable=True, default=0))


def downgrade() -> None:
    """Remove non-employment income fields from income_taxes table."""
    op.drop_column('income_taxes', 'other_taxable_income')
    op.drop_column('income_taxes', 'traditional_401k_distribution')
    op.drop_column('income_taxes', 'traditional_ira_distribution')
    op.drop_column('income_taxes', 'pension_income')
    op.drop_column('income_taxes', 'social_security_income')

