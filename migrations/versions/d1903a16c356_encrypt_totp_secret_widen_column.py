"""encrypt totp_secret widen column

Revision ID: d1903a16c356
Revises: 530d6dd3a280
Create Date: 2026-06-22 22:30:09.379825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1903a16c356'
down_revision: Union[str, Sequence[str], None] = '530d6dd3a280'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen users.totp_secret to hold Fernet ciphertext (encrypted at rest)."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "totp_secret",
            existing_type=sa.String(length=64),
            type_=sa.String(length=255),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Narrow back to 64 (note: existing ciphertext will not fit — decrypt first if reverting)."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "totp_secret",
            existing_type=sa.String(length=255),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
