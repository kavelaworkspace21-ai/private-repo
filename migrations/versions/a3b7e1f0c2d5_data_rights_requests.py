"""add data_rights_requests table

Revision ID: a3b7e1f0c2d5
Revises: f2a1c9d4e7b3
Create Date: 2026-06-23 12:30:00.000000

LSAI-LEGAL-05 — DPDP data-principal rights request tracker.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b7e1f0c2d5"
down_revision: Union[str, Sequence[str], None] = "f2a1c9d4e7b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_rights_requests",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), index=True, nullable=True),
        sa.Column("user_id", sa.Integer(), index=True, nullable=False),
        sa.Column("request_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="received"),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("resolver_note", sa.Text(), nullable=True),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("data_rights_requests")
