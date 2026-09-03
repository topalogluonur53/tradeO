"""update existing user strategy defaults

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-03 23:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update all existing users with old tight defaults to new relaxed defaults
    op.execute("UPDATE users SET strategy_bollinger_width = 0.15 WHERE strategy_bollinger_width = 0.08")
    op.execute("UPDATE users SET strategy_rsi_min = 25.0 WHERE strategy_rsi_min = 35.0")
    op.execute("UPDATE users SET strategy_rsi_max = 78.0 WHERE strategy_rsi_max = 70.0")
    op.execute("UPDATE users SET strategy_volume_multiplier = 0.3 WHERE strategy_volume_multiplier = 0.6")


def downgrade() -> None:
    op.execute("UPDATE users SET strategy_bollinger_width = 0.08 WHERE strategy_bollinger_width = 0.15")
    op.execute("UPDATE users SET strategy_rsi_min = 35.0 WHERE strategy_rsi_min = 25.0")
    op.execute("UPDATE users SET strategy_rsi_max = 70.0 WHERE strategy_rsi_max = 78.0")
    op.execute("UPDATE users SET strategy_volume_multiplier = 0.6 WHERE strategy_volume_multiplier = 0.3")
