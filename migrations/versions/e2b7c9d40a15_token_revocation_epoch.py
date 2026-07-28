"""token revocation epoch (users.tokens_valid_from)

JWTs are stateless: once issued, a token is valid until it expires, and nothing the user
does can recall it. That means a stolen access/refresh token survived the victim's password
reset — the very action a compromised user takes first — for up to the refresh window.

`tokens_valid_from` is the revocation epoch. Tokens carry `iat`; any token issued before
this timestamp is refused. One column update invalidates every outstanding token for that
user, with no blacklist to store, grow, or purge.

Nullable by design: NULL means "nothing has ever been revoked for this user", which is the
correct reading for every existing row.

Revision ID: e2b7c9d40a15
Revises: c7f4a2e8b103
Create Date: 2026-07-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2b7c9d40a15"
down_revision: Union[str, Sequence[str], None] = "c7f4a2e8b103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("tokens_valid_from", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "tokens_valid_from")
