"""add_tax_year_to_income_taxes

Revision ID: c7270b46308a
Revises: f1a4380655fe
Create Date: 2025-12-13 20:46:34.998200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c7270b46308a'
down_revision: Union[str, Sequence[str], None] = 'f1a4380655fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema."""
    # Add tax_year column to income_taxes if it doesn't exist
    if not column_exists('income_taxes', 'tax_year'):
        with op.batch_alter_table('income_taxes', schema=None) as batch_op:
            batch_op.add_column(sa.Column('tax_year', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if column_exists('income_taxes', 'tax_year'):
        with op.batch_alter_table('income_taxes', schema=None) as batch_op:
            batch_op.drop_column('tax_year')
