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
        column('is_admin', sa.Boolean)
    )
    
    # Check if 'onur' already exists
    res = session.execute(sa.select(users_table).where(users_table.c.username == 'onur')).fetchone()
    if not res:
        hashed = bcrypt.hashpw(b"12345353*", bcrypt.gensalt()).decode()
        session.execute(users_table.insert().values(
            username='onur',
            hashed_password=hashed,
            is_active=True,
            is_admin=True
        ))
    session.commit()


def downgrade() -> None:
    # We won't delete the user in downgrade, just revert the schema
    op.drop_column('users', 'is_admin')
    op.alter_column('users', 'username', new_column_name='email')
