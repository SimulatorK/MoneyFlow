"""Add portfolio allocation and Monte Carlo scenarios

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2024-12-14

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add portfolio allocation columns to networth_contributions
    with op.batch_alter_table('networth_contributions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stocks_pct', sa.Float(), nullable=True, default=80.0))
        batch_op.add_column(sa.Column('bonds_pct', sa.Float(), nullable=True, default=15.0))
        batch_op.add_column(sa.Column('cash_pct', sa.Float(), nullable=True, default=5.0))
    
    # Set default values for existing rows
    op.execute("UPDATE networth_contributions SET stocks_pct = 80.0 WHERE stocks_pct IS NULL")
    op.execute("UPDATE networth_contributions SET bonds_pct = 15.0 WHERE bonds_pct IS NULL")
    op.execute("UPDATE networth_contributions SET cash_pct = 5.0 WHERE cash_pct IS NULL")
    
    # Create Monte Carlo scenarios table
    op.create_table(
        'monte_carlo_scenarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('projection_years', sa.Integer(), nullable=True),
        sa.Column('num_simulations', sa.Integer(), nullable=True),
        sa.Column('settings_json', sa.Text(), nullable=True),
        sa.Column('results_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_monte_carlo_scenarios_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_monte_carlo_scenarios'))
    )
    with op.batch_alter_table('monte_carlo_scenarios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_monte_carlo_scenarios_id'), ['id'], unique=False)


def downgrade() -> None:
    # Drop Monte Carlo scenarios table
    with op.batch_alter_table('monte_carlo_scenarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_monte_carlo_scenarios_id'))
    op.drop_table('monte_carlo_scenarios')
    
    # Remove portfolio allocation columns
    with op.batch_alter_table('networth_contributions', schema=None) as batch_op:
        batch_op.drop_column('cash_pct')
        batch_op.drop_column('bonds_pct')
        batch_op.drop_column('stocks_pct')

