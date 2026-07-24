"""add tenant verification fields

Revision ID: b4c8f2a1d6e9
Revises: a3b7e1f0c2d5
Create Date: 2026-06-23 13:00:00.000000

LSAI-LEGAL-07 — advocate/firm verification (founder-approved for the closed beta).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4c8f2a1d6e9"
down_revision: Union[str, Sequence[str], None] = "a3b7e1f0c2d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("verification_status", sa.String(length=20),
                                      nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("jurisdiction", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("bar_enrolment", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("verification_note", sa.String(length=400), nullable=True))
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.drop_column("verified_at")
        batch_op.drop_column("verification_note")
        batch_op.drop_column("bar_enrolment")
        batch_op.drop_column("jurisdiction")
        batch_op.drop_column("verification_status")
