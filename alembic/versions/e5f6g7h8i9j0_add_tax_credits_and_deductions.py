"""Add tax credits and deductions to income_taxes

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2025-12-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tax credits and deductions columns to income_taxes table."""
    with op.batch_alter_table('income_taxes', schema=None) as batch_op:
        # Tax Credits
        batch_op.add_column(sa.Column('child_tax_credit', sa.Float(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('education_credits', sa.Float(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('other_credits', sa.Float(), nullable=True, server_default='0'))
        
        # Additional Itemized Deductions
        batch_op.add_column(sa.Column('mortgage_interest_deduction', sa.Float(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('property_tax_deduction', sa.Float(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('charitable_deduction', sa.Float(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('student_loan_interest', sa.Float(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('other_deductions', sa.Float(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('use_itemized', sa.Boolean(), nullable=True, server_default='0'))


def downgrade() -> None:
    """Remove tax credits and deductions columns from income_taxes table."""
    with op.batch_alter_table('income_taxes', schema=None) as batch_op:
        batch_op.drop_column('use_itemized')
        batch_op.drop_column('other_deductions')
        batch_op.drop_column('student_loan_interest')
        batch_op.drop_column('charitable_deduction')
        batch_op.drop_column('property_tax_deduction')
        batch_op.drop_column('mortgage_interest_deduction')
        batch_op.drop_column('other_credits')
        batch_op.drop_column('education_credits')
        batch_op.drop_column('child_tax_credit')

