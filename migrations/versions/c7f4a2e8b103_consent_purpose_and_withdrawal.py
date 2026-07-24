"""consent purpose, scope and withdrawal (DPDP: purpose-limited + withdrawable)

Adds the fields a DPDP-defensible consent record needs beyond "granted at a version":
  purpose      — what the data is used FOR
  scope        — what data the grant covers
  withdrawn_at — when the data principal withdrew it

Withdrawal is modelled as a timestamp on the existing row rather than a delete, so the
grant survives as audit evidence that consent existed for the period it was relied on,
while ceasing to authorise anything from the moment it is set.

All three are nullable: existing rows predate the concept and must not be invented. A NULL
withdrawn_at means "not withdrawn", which is the correct reading of historical grants.

Revision ID: c7f4a2e8b103
Revises: 81665ba86789
Create Date: 2026-07-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7f4a2e8b103"
down_revision: Union[str, Sequence[str], None] = "81665ba86789"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("consent_records", sa.Column("purpose", sa.String(length=60), nullable=True))
    op.add_column("consent_records", sa.Column("scope", sa.String(length=60), nullable=True))
    op.add_column("consent_records", sa.Column("withdrawn_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("consent_records", "withdrawn_at")
    op.drop_column("consent_records", "scope")
    op.drop_column("consent_records", "purpose")
