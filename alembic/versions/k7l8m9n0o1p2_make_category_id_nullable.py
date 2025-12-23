"""Make category_id nullable in expenses table

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
Create Date: 2025-12-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k7l8m9n0o1p2'
down_revision: Union[str, None] = 'j6k7l8m9n0o1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite doesn't support ALTER COLUMN directly, so we need to recreate the table
    # For SQLite, we'll use batch operations
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.alter_column('category_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)


def downgrade() -> None:
    # Note: downgrade may fail if there are NULL category_id values
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.alter_column('category_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

