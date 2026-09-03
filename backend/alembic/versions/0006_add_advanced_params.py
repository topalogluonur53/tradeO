"""add advanced strategy params

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-03 23:14:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('strategy_macd_enabled', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('users', sa.Column('strategy_stoch_enabled', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('users', sa.Column('mtf_enabled', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('users', sa.Column('trailing_stop_enabled', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('users', sa.Column('trailing_stop_distance_pct', sa.Float(), nullable=True, server_default='0.03'))


def downgrade() -> None:
    op.drop_column('users', 'trailing_stop_distance_pct')
    op.drop_column('users', 'trailing_stop_enabled')
    op.drop_column('users', 'mtf_enabled')
    op.drop_column('users', 'strategy_stoch_enabled')
    op.drop_column('users', 'strategy_macd_enabled')
