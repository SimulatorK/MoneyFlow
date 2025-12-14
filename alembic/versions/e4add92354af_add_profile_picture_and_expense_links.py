"""add_profile_picture_and_expense_links

Revision ID: e4add92354af
Revises: 24987ef4ea7c
Create Date: 2025-12-13 18:07:29.589116

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4add92354af'
down_revision: Union[str, Sequence[str], None] = '24987ef4ea7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add columns to fixed_costs (foreign keys handled via column definition for SQLite)
    with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expense_category_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('expense_subcategory_id', sa.Integer(), nullable=True))

    # Add columns to users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('profile_picture', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('profile_picture_type', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('profile_picture_type')
        batch_op.drop_column('profile_picture')

    with op.batch_alter_table('fixed_costs', schema=None) as batch_op:
        batch_op.drop_column('expense_subcategory_id')
        batch_op.drop_column('expense_category_id')
