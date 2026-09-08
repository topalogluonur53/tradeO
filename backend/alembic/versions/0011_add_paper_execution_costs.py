"""add realistic paper execution costs

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_positions",
        sa.Column("entry_fee", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "paper_trades",
        sa.Column("fees_paid", sa.Float(), nullable=False, server_default="0"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("paper_positions", "entry_fee", server_default=None)
        op.alter_column("paper_trades", "fees_paid", server_default=None)

    # Revision 0008 installed an all-in aggressive template for every user.
    # Rebalance only rows that still exactly match that template so later user
    # customizations are never overwritten.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET risk_per_trade = 0.005,
                max_single_position_pct = 0.10,
                max_total_exposure_pct = 0.30,
                max_open_positions = 3,
                daily_loss_limit_pct = 0.02,
                max_drawdown_limit_pct = 0.08,
                min_risk_reward = 1.5,
                cooldown_after_losses = 3,
                strategy_bollinger_width = 0.15,
                strategy_rsi_min = 25.0,
                strategy_rsi_max = 78.0,
                strategy_volume_multiplier = 0.3
            WHERE risk_per_trade = 0.05
              AND max_single_position_pct = 0.50
              AND max_total_exposure_pct = 1.00
              AND max_open_positions = 15
              AND min_risk_reward = 1.0
              AND cooldown_after_losses = 0
              AND strategy_bollinger_width = 1.50
              AND strategy_rsi_min = 10.0
              AND strategy_rsi_max = 90.0
              AND strategy_volume_multiplier = 0.1
            """
        )
    )


def downgrade() -> None:
    op.drop_column("paper_trades", "fees_paid")
    op.drop_column("paper_positions", "entry_fee")
