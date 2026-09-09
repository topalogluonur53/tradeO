"""enable defensive paper-trading risk defaults

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve customized accounts. Only the current balanced template gets
    # profit protection enabled automatically.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET trailing_stop_enabled = true
            WHERE risk_per_trade = 0.005
              AND max_single_position_pct = 0.10
              AND max_total_exposure_pct = 0.30
              AND max_open_positions = 3
              AND daily_loss_limit_pct = 0.02
              AND max_drawdown_limit_pct = 0.08
              AND trailing_stop_enabled = false
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE users
            SET trailing_stop_enabled = false
            WHERE risk_per_trade = 0.005
              AND max_single_position_pct = 0.10
              AND max_total_exposure_pct = 0.30
              AND max_open_positions = 3
              AND daily_loss_limit_pct = 0.02
              AND max_drawdown_limit_pct = 0.08
              AND trailing_stop_enabled = true
            """
        )
    )
