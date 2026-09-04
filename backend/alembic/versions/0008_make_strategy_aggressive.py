"""make strategy very aggressive

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-04 13:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Set aggressive limits for all users
    op.execute("UPDATE users SET risk_per_trade = 0.05")
    op.execute("UPDATE users SET max_single_position_pct = 0.50")
    op.execute("UPDATE users SET max_total_exposure_pct = 1.00")
    op.execute("UPDATE users SET max_open_positions = 15")
    op.execute("UPDATE users SET min_risk_reward = 1.0")
    op.execute("UPDATE users SET cooldown_after_losses = 0")
    
    op.execute("UPDATE users SET strategy_bollinger_width = 1.50")
    op.execute("UPDATE users SET strategy_rsi_min = 10.0")
    op.execute("UPDATE users SET strategy_rsi_max = 90.0")
    op.execute("UPDATE users SET strategy_volume_multiplier = 0.1")
    op.execute("UPDATE users SET strategy_macd_enabled = false")
    op.execute("UPDATE users SET strategy_stoch_enabled = false")
    op.execute("UPDATE users SET mtf_enabled = false")


def downgrade() -> None:
    # Revert to previous defaults
    op.execute("UPDATE users SET risk_per_trade = 0.005")
    op.execute("UPDATE users SET max_single_position_pct = 0.10")
    op.execute("UPDATE users SET max_total_exposure_pct = 0.30")
    op.execute("UPDATE users SET max_open_positions = 3")
    op.execute("UPDATE users SET min_risk_reward = 1.5")
    op.execute("UPDATE users SET cooldown_after_losses = 3")
    
    op.execute("UPDATE users SET strategy_bollinger_width = 0.15")
    op.execute("UPDATE users SET strategy_rsi_min = 25.0")
    op.execute("UPDATE users SET strategy_rsi_max = 78.0")
    op.execute("UPDATE users SET strategy_volume_multiplier = 0.3")
