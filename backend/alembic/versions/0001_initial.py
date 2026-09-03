"""initial

Revision ID: 0001
Revises: 
Create Date: 2026-09-03 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('binance_api_key', sa.String(length=255), nullable=True),
        sa.Column('binance_api_secret', sa.String(length=255), nullable=True),
        sa.Column('risk_per_trade', sa.Float(), nullable=False),
        sa.Column('max_single_position_pct', sa.Float(), nullable=False),
        sa.Column('max_total_exposure_pct', sa.Float(), nullable=False),
        sa.Column('max_open_positions', sa.Integer(), nullable=False),
        sa.Column('daily_loss_limit_pct', sa.Float(), nullable=False),
        sa.Column('max_drawdown_limit_pct', sa.Float(), nullable=False),
        sa.Column('min_risk_reward', sa.Float(), nullable=False),
        sa.Column('cooldown_after_losses', sa.Integer(), nullable=False),
        sa.Column('is_automation_enabled', sa.Boolean(), nullable=False),
        sa.Column('trading_mode', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
