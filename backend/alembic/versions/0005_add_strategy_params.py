"""add strategy params

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-03 23:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('strategy_bollinger_width', sa.Float(), nullable=True, server_default='0.08'))
    op.add_column('users', sa.Column('strategy_rsi_min', sa.Float(), nullable=True, server_default='35.0'))
    op.add_column('users', sa.Column('strategy_rsi_max', sa.Float(), nullable=True, server_default='70.0'))
    op.add_column('users', sa.Column('strategy_volume_multiplier', sa.Float(), nullable=True, server_default='0.6'))


def downgrade() -> None:
    op.drop_column('users', 'strategy_volume_multiplier')
    op.drop_column('users', 'strategy_rsi_max')
    op.drop_column('users', 'strategy_rsi_min')
    op.drop_column('users', 'strategy_bollinger_width')
