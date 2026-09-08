"""enable stronger confluence strategy defaults

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update only the untouched balanced template. Explicit user tuning is
    # preserved, while existing default accounts receive stronger volume and
    # higher-timeframe confirmation.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET strategy_volume_multiplier = 0.8,
                mtf_enabled = true
            WHERE strategy_bollinger_width = 0.15
              AND strategy_rsi_min = 25.0
              AND strategy_rsi_max = 78.0
              AND strategy_volume_multiplier = 0.3
              AND mtf_enabled = false
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE users
            SET strategy_volume_multiplier = 0.3,
                mtf_enabled = false
            WHERE strategy_volume_multiplier = 0.8
              AND mtf_enabled = true
            """
        )
    )
