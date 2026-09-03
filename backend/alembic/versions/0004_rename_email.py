"""rename email to username and add admin

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03 20:48:00.000000

"""
from typing import Sequence, Union
import bcrypt

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename column email to username
    op.alter_column('users', 'email', new_column_name='username')
    
    # Add is_admin column
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False))
    
    # Seed the admin user 'onur'
    bind = op.get_bind()
    session = Session(bind=bind)
    
    users_table = table('users',
        column('id', sa.Integer),
        column('username', sa.String),
        column('hashed_password', sa.String),
        column('is_active', sa.Boolean),
        column('is_admin', sa.Boolean),
        column('risk_per_trade', sa.Float),
        column('max_single_position_pct', sa.Float),
        column('max_total_exposure_pct', sa.Float),
        column('max_open_positions', sa.Integer),
        column('daily_loss_limit_pct', sa.Float),
        column('max_drawdown_limit_pct', sa.Float),
        column('min_risk_reward', sa.Float),
        column('cooldown_after_losses', sa.Integer),
        column('is_automation_enabled', sa.Boolean),
        column('trading_mode', sa.String),
        column('trading_halted', sa.Boolean),
        column('halt_reason', sa.String)
    )
    
    # Check if 'onur' already exists
    res = session.execute(sa.select(users_table).where(users_table.c.username == 'onur')).fetchone()
    if not res:
        hashed = bcrypt.hashpw(b"12345353*", bcrypt.gensalt()).decode()
        session.execute(users_table.insert().values(
            username='onur',
            hashed_password=hashed,
            is_active=True,
            is_admin=True,
            risk_per_trade=0.005,
            max_single_position_pct=0.10,
            max_total_exposure_pct=0.30,
            max_open_positions=3,
            daily_loss_limit_pct=0.02,
            max_drawdown_limit_pct=0.08,
            min_risk_reward=1.5,
            cooldown_after_losses=3,
            is_automation_enabled=False,
            trading_mode='paper',
            trading_halted=False,
            halt_reason='PAPER_MODE_READY'
        ))
    session.commit()


def downgrade() -> None:
    # We won't delete the user in downgrade, just revert the schema
    op.drop_column('users', 'is_admin')
    op.alter_column('users', 'username', new_column_name='email')
