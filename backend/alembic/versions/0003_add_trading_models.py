"""add trading models

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03 20:39:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PaperPortfolios
    op.create_table('paper_portfolios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('cash', sa.Float(), nullable=False),
        sa.Column('equity', sa.Float(), nullable=False),
        sa.Column('peak_equity', sa.Float(), nullable=False),
        sa.Column('current_exposure', sa.Float(), nullable=False),
        sa.Column('daily_pnl', sa.Float(), nullable=False),
        sa.Column('consecutive_losses', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_paper_portfolios_id'), 'paper_portfolios', ['id'], unique=False)

    # PaperPositions
    op.create_table('paper_positions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('current_price', sa.Float(), nullable=False),
        sa.Column('stop_loss', sa.Float(), nullable=False),
        sa.Column('take_profit', sa.Float(), nullable=False),
        sa.Column('unrealized_pnl', sa.Float(), nullable=False),
        sa.Column('unrealized_pnl_pct', sa.Float(), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('strategy', sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(['portfolio_id'], ['paper_portfolios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_paper_positions_id'), 'paper_positions', ['id'], unique=False)

    # PaperTrades
    op.create_table('paper_trades',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=False),
        sa.Column('realized_pnl', sa.Float(), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exit_reason', sa.String(length=255), nullable=False),
        sa.Column('strategy', sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(['portfolio_id'], ['paper_portfolios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_paper_trades_id'), 'paper_trades', ['id'], unique=False)

    # AutomationStates
    op.create_table('automation_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('running', sa.Boolean(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('interval', sa.String(length=10), nullable=False),
        sa.Column('exchange', sa.String(length=50), nullable=False),
        sa.Column('last_cycle_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_action', sa.String(length=100), nullable=False),
        sa.Column('last_reason', sa.String(length=255), nullable=False),
        sa.Column('last_signal_json', sa.Text(), nullable=True),
        sa.Column('last_risk_decision_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_automation_states_id'), 'automation_states', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('automation_states')
    op.drop_table('paper_trades')
    op.drop_table('paper_positions')
    op.drop_table('paper_portfolios')
