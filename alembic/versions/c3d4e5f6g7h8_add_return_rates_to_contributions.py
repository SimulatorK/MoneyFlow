"""Add return rates to contributions

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2025-12-14 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add expected_return and interest_rate columns to networth_contributions."""
    with op.batch_alter_table('networth_contributions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expected_return', sa.Float(), nullable=True, default=7.0))
        batch_op.add_column(sa.Column('interest_rate', sa.Float(), nullable=True, default=0))


def downgrade() -> None:
    """Remove expected_return and interest_rate columns from networth_contributions."""
    with op.batch_alter_table('networth_contributions', schema=None) as batch_op:
        batch_op.drop_column('interest_rate')
        batch_op.drop_column('expected_return')

