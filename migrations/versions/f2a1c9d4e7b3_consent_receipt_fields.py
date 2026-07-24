"""add consent receipt fields (user_agent, acceptance_source)

Revision ID: f2a1c9d4e7b3
Revises: d1903a16c356
Create Date: 2026-06-23 12:00:00.000000

LSAI-LEGAL-03 — make consent provable: store the user-agent and the acceptance source
(registration | consent_page | policy_update) alongside the existing source IP + versions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a1c9d4e7b3"
down_revision: Union[str, Sequence[str], None] = "d1903a16c356"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("consent_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_agent", sa.String(length=400), nullable=True))
        batch_op.add_column(sa.Column("acceptance_source", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("consent_records", schema=None) as batch_op:
        batch_op.drop_column("acceptance_source")
        batch_op.drop_column("user_agent")
