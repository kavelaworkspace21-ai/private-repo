from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.auth.config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    now = datetime.now(timezone.utc)
    payload["exp"] = now + expires_delta
    # `iat` makes every token comparable against User.tokens_valid_from, which is how
    # revocation works here: bumping that column invalidates every token issued before it.
    # Without an issued-at there is nothing to compare, so a stolen token would stay valid
    # for its full lifetime even after the victim reset their password.
    payload["iat"] = now
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: int, role: str) -> str:
    return _create_token(
        {"sub": str(user_id), "role": role, "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        {"sub": str(user_id), "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


# 15 minutes: a reset link sits in an inbox, and inboxes get forwarded, synced
# to shared devices, and breached. Shorter is strictly better here.
PASSWORD_RESET_EXPIRE_MINUTES = 15


def revocation_epoch() -> "datetime":
    """The value to store in User.tokens_valid_from when revoking sessions.

    Truncated DOWN to the whole second, deliberately.

    `iat` has one-second resolution, so this leaves a residual window: a token issued
    earlier in the SAME second as the revocation survives. Rounding up would close that,
    but it also breaks legitimate flows — a firm invite where the member sets a password
    and is logged straight in, or any reset-then-login that completes inside one second,
    would be rejected and look like a broken product.

    The threat this defends against is a token stolen minutes, hours or days ago; none of
    that is inside the current second. Trading a sub-second window no attacker can aim at
    for a flow that always works is the right way round.
    """
    from app.util.time import utcnow
    return utcnow().replace(microsecond=0)


def password_fingerprint(hashed_password: str) -> str:
    """Short digest of the CURRENT password hash, embedded in reset tokens.

    This is what makes a reset link single-use, and it needs no extra storage and no clock
    comparison: the moment the password changes the hash changes, so the fingerprint in any
    outstanding link stops matching and the link is dead. (A timestamp epoch cannot do this
    job — `iat` has one-second resolution, so a token minted and consumed within the same
    second is indistinguishable from a replay.)

    An invited firm member has no password yet, so the fingerprint of "no password" is a
    stable constant — their invite link stays valid until they use it, and dies the moment
    they set a password, which is exactly the single-use behaviour we want.
    """
    import hashlib
    return hashlib.sha256((hashed_password or "<unset>").encode()).hexdigest()[:16]


def create_reset_token(user_id: int, hashed_password: str) -> str:
    """Short-lived, single-purpose, single-USE token for password reset."""
    return _create_token(
        {"sub": str(user_id), "type": "reset", "pwf": password_fingerprint(hashed_password)},
        timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES),
    )


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
