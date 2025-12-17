"""Add return rates to contributions

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2025-12-14 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add expected_return and interest_rate columns to networth_contributions."""
    if table_exists('networth_contributions'):
        if not column_exists('networth_contributions', 'expected_return'):
            with op.batch_alter_table('networth_contributions', schema=None) as batch_op:
                batch_op.add_column(sa.Column('expected_return', sa.Float(), nullable=True, default=7.0))
        
        if not column_exists('networth_contributions', 'interest_rate'):
            with op.batch_alter_table('networth_contributions', schema=None) as batch_op:
                batch_op.add_column(sa.Column('interest_rate', sa.Float(), nullable=True, default=0))


def downgrade() -> None:
    """Remove expected_return and interest_rate columns from networth_contributions."""
    if table_exists('networth_contributions'):
        for col_name in ['interest_rate', 'expected_return']:
            if column_exists('networth_contributions', col_name):
                with op.batch_alter_table('networth_contributions', schema=None) as batch_op:
                    batch_op.drop_column(col_name)
