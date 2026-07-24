"""add user soul-violation ejection fields (is_banned, banned_reason, banned_at)

Revision ID: d7e3b1a9c4f2
Revises: c5d9a3e2f7b1
Create Date: 2026-06-24 14:00:00.000000

Owner directive 2026-06-24 — eject users who attempt to use Juriscite against the soul.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e3b1a9c4f2"
down_revision: Union[str, Sequence[str], None] = "c5d9a3e2f7b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_banned", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column("banned_reason", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("banned_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("banned_at")
        batch_op.drop_column("banned_reason")
        batch_op.drop_column("is_banned")
