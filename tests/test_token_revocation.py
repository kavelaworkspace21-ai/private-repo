"""Password-reset tokens must be single-use, and a reset must kill existing sessions.

Two defects this pins:

  * Reset tokens were replayable. The token is a JWT with `type: reset` and an expiry, and
    nothing marked it consumed. Anyone who saw the reset email — a forwarded message, a
    shared device, a synced inbox, a mail-provider breach — could keep re-resetting the
    password until it expired, locking the owner out of their own account.
  * A password reset left every previously issued token alive. Resetting the password is
    the first thing a compromised user does; leaving the attacker's stolen session valid
    for the remaining refresh window defeats the point.

Both are closed by one mechanism: tokens carry `iat`, users carry a revocation epoch, and
a token issued before the epoch is refused.
"""
import time

from app.auth.security import create_access_token, create_reset_token, decode_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from tests.conftest import auth, register_and_login


def _db():
    return next(app.dependency_overrides[get_db]())


def _user(db, email):
    return db.query(User).filter(User.email == email).first()


def test_tokens_carry_an_issued_at_claim():
    """Without `iat` there is nothing to compare against the revocation epoch."""
    assert decode_token(create_access_token(1, "advocate")).get("iat")
    assert decode_token(create_reset_token(1, 'someBcryptHash')).get("iat")


def test_reset_token_cannot_be_replayed(client):
    email = "replay@firm.com"
    register_and_login(client, email)
    db = _db()
    token = (lambda u: create_reset_token(u.id, u.hashed_password))(_user(db, email))

    first = client.post("/api/auth/reset-password",
                        json={"token": token, "new_password": "FirstReset123!"})
    assert first.status_code == 200, first.text

    # The attacker replays the same link — this used to succeed and let them take the
    # account over by resetting the password again.
    second = client.post("/api/auth/reset-password",
                         json={"token": token, "new_password": "AttackerOwned456!"})
    assert second.status_code == 400, "reset token was accepted a second time"

    # and the password the legitimate user set is the one that works
    assert client.post("/api/auth/login",
                       json={"email": email, "password": "FirstReset123!"}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"email": email, "password": "AttackerOwned456!"}).status_code == 401


def test_password_reset_revokes_existing_sessions(client):
    """The stolen-token case: resetting the password must end the attacker's session."""
    email = "revoke@firm.com"
    stolen = register_and_login(client, email)
    assert client.get("/api/auth/me", headers=auth(stolen)).status_code == 200

    db = _db()
    time.sleep(1.1)                      # iat has 1-second resolution
    token = (lambda u: create_reset_token(u.id, u.hashed_password))(_user(db, email))
    assert client.post("/api/auth/reset-password",
                       json={"token": token, "new_password": "BrandNewPass789!"}).status_code == 200

    assert client.get("/api/auth/me", headers=auth(stolen)).status_code == 401, (
        "a token issued before the password reset still works")


def test_logout_all_revokes_every_session(client):
    email = "logoutall@firm.com"
    tok_a = register_and_login(client, email)
    time.sleep(1.1)
    tok_b = client.post("/api/auth/login",
                        json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]

    assert client.post("/api/auth/logout-all", headers=auth(tok_b)).status_code == 200
    # The other device's session — the one a user signing out everywhere actually cares
    # about — is dead. tok_b was minted in the same second as the revocation and may
    # survive that second by design (see revocation_epoch); the client discards it anyway.
    assert client.get("/api/auth/me", headers=auth(tok_a)).status_code == 401


def test_tokens_issued_after_a_revocation_still_work(client):
    """Revocation must not permanently lock the account out."""
    email = "afterrevoke@firm.com"
    register_and_login(client, email)
    db = _db()
    token = (lambda u: create_reset_token(u.id, u.hashed_password))(_user(db, email))
    client.post("/api/auth/reset-password",
                json={"token": token, "new_password": "FreshPass321!"})

    fresh = client.post("/api/auth/login",
                        json={"email": email, "password": "FreshPass321!"}).json()["access_token"]
    assert client.get("/api/auth/me", headers=auth(fresh)).status_code == 200


def test_reset_link_expires_within_fifteen_minutes():
    from app.auth.security import PASSWORD_RESET_EXPIRE_MINUTES
    assert PASSWORD_RESET_EXPIRE_MINUTES <= 15


def test_a_token_with_no_iat_is_refused_after_a_revocation():
    """Fail closed: a token predating this mechanism cannot prove it post-dates a revocation."""
    from datetime import datetime

    from app.auth.dependencies import token_revoked

    class _U:
        tokens_valid_from = datetime(2026, 1, 1)

    assert token_revoked(_U(), {"sub": "1"}) is True
    assert token_revoked(_U(), {"sub": "1", "iat": int(datetime(2025, 1, 1).timestamp())}) is True


def test_untouched_accounts_are_unaffected():
    """No revocation ever performed => every valid token keeps working."""
    from app.auth.dependencies import token_revoked

    class _U:
        tokens_valid_from = None

    assert token_revoked(_U(), {"sub": "1"}) is False
