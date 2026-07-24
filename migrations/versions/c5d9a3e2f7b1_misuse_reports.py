"""add misuse_reports table

Revision ID: c5d9a3e2f7b1
Revises: b4c8f2a1d6e9
Create Date: 2026-06-23 13:30:00.000000

LSAI-LEGAL-16 — user misuse/abuse reporting.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d9a3e2f7b1"
down_revision: Union[str, Sequence[str], None] = "b4c8f2a1d6e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "misuse_reports",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), index=True, nullable=True),
        sa.Column("reporter_user_id", sa.Integer(), index=True, nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="received"),
        sa.Column("resolver_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("misuse_reports")
