"""store each user's paper starting capital

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_portfolios",
        sa.Column("initial_equity", sa.Float(), nullable=False, server_default="10000"),
    )
    # SQLite cannot DROP a column default with ALTER TABLE. The default is
    # harmless there (and is needed while adding a non-null column); other
    # database engines retain the intended no-default schema.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("paper_portfolios", "initial_equity", server_default=None)


def downgrade() -> None:
    op.drop_column("paper_portfolios", "initial_equity")
