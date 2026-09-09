"""add position tracking fields

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-09 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table('paper_positions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('initial_stop_loss', sa.Float(), nullable=False, server_default='0.0'))
        batch_op.add_column(sa.Column('highest_price', sa.Float(), nullable=False, server_default='0.0'))
        batch_op.add_column(sa.Column('bars_held', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('last_counted_close_time', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('entry_candle_close_time', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('stop_type', sa.String(length=20), nullable=False, server_default='INITIAL'))

def downgrade() -> None:
    with op.batch_alter_table('paper_positions', schema=None) as batch_op:
        batch_op.drop_column('stop_type')
        batch_op.drop_column('entry_candle_close_time')
        batch_op.drop_column('last_counted_close_time')
        batch_op.drop_column('bars_held')
        batch_op.drop_column('highest_price')
        batch_op.drop_column('initial_stop_loss')
