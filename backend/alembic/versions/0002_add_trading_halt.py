"""add trading halt fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03 20:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('trading_halted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('halt_reason', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'halt_reason')
    op.drop_column('users', 'trading_halted')
