"""store equal paper position allocation settings

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_states",
        sa.Column("position_count", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "automation_states",
        sa.Column("allocation_usd", sa.Float(), nullable=False, server_default="0"),
    )
    # SQLite cannot DROP defaults through ALTER COLUMN. Leaving these defaults
    # in place is safe and lets local paper-trading startup migrate cleanly.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("automation_states", "position_count", server_default=None)
        op.alter_column("automation_states", "allocation_usd", server_default=None)


def downgrade() -> None:
    op.drop_column("automation_states", "allocation_usd")
    op.drop_column("automation_states", "position_count")
