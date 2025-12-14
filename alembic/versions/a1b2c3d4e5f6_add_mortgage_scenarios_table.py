"""Add mortgage_scenarios table

Revision ID: a1b2c3d4e5f6
Revises: f1a4380655fe
Create Date: 2025-12-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = ('b758a9349f0c', 'f1a4380655fe')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create mortgage_scenarios table for storing saved mortgage calculator scenarios."""
    op.create_table(
        'mortgage_scenarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('compare_mode', sa.Boolean(), nullable=True, default=False),
        sa.Column('scenario_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_mortgage_scenarios_user_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mortgage_scenarios_id'), 'mortgage_scenarios', ['id'], unique=False)


def downgrade() -> None:
    """Drop mortgage_scenarios table."""
    op.drop_index(op.f('ix_mortgage_scenarios_id'), table_name='mortgage_scenarios')
    op.drop_table('mortgage_scenarios')

