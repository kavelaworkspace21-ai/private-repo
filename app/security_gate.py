"""Fail-closed secret sanity gate — refuse to boot with unsafe signing material.

WHY THIS EXISTS
---------------
`app/auth/config.py` reads `JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")`.
That default is a placeholder published in this repository, and it fails **open**: with the
variable unset the app boots normally, looks healthy, and signs every access token with a
string any reader of the source knows. Anyone can then forge a token for any user in any
tenant — a complete authentication bypass with no error and nothing in the logs.

It compounds. `app/db/crypto.py::_fernet()` falls back to a key *derived from JWT_SECRET*
when `FIELD_ENCRYPTION_KEY` is unset. So the same placeholder also becomes the encryption
key protecting `totp_secret` at rest: the second factor is decryptable by anyone holding
the source. One unset variable defeats both authentication and encryption at once.

`app.ops.release.preflight()` already refuses to DEPLOY without these. But preflight is a
deploy-time gate an operator has to run — it does nothing for `uvicorn app.main:app`
started by hand, by a systemd unit, or by a container that skips it. This gate closes that
hole at BOOT, which is the only moment guaranteed to happen.

Called from `app/main.py` beside `assert_prohibited_disabled()` and `assert_soul_intact()`.
"""
from __future__ import annotations

import os

# The published placeholder from app/auth/config.py. Treated as "no secret at all".
PLACEHOLDER_JWT_SECRET = "change-me-in-production"

# HS256 signing key floor. Shorter than the 256-bit hash it feeds adds no security and is
# well within brute-force range for a determined attacker with a captured token.
MIN_JWT_SECRET_LEN = 32

# Environments permitted to run with weak/absent secrets. Anything else — including an
# UNSET ENVIRONMENT — is treated as production, so forgetting to set it fails closed
# rather than open. (app/observability.py already defaults ENVIRONMENT to "production".)
NON_PRODUCTION = {"dev", "development", "local", "test", "testing", "ci"}


def current_environment() -> str:
    return os.getenv("ENVIRONMENT", "production").strip().lower()


def is_production() -> bool:
    return current_environment() not in NON_PRODUCTION


def secret_problems() -> list[str]:
    """Problems with the signing/encryption material. Empty list = safe.

    Never returns or logs a secret VALUE — only the name and the nature of the problem.
    """
    problems: list[str] = []

    jwt_secret = os.getenv("JWT_SECRET") or ""
    if not jwt_secret:
        problems.append(
            "JWT_SECRET is not set — the app would fall back to the placeholder published "
            "in app/auth/config.py, making every access token forgeable")
    elif jwt_secret == PLACEHOLDER_JWT_SECRET:
        problems.append(
            "JWT_SECRET is still the published placeholder — every access token is "
            "forgeable by anyone who has read this repository")
    elif len(jwt_secret) < MIN_JWT_SECRET_LEN:
        problems.append(
            f"JWT_SECRET is only {len(jwt_secret)} chars; minimum is {MIN_JWT_SECRET_LEN}")

    if not os.getenv("FIELD_ENCRYPTION_KEY"):
        problems.append(
            "FIELD_ENCRYPTION_KEY is not set — app/db/crypto.py would derive the "
            "at-rest key from JWT_SECRET, so stored TOTP secrets share the fate of the "
            "signing key instead of being independently protected")

    return problems


def assert_secrets_sane() -> None:
    """Refuse to boot in production with unsafe secrets. Warn loudly elsewhere.

    Raises RuntimeError rather than logging, because a warning at startup scrolls past and
    the failure it describes is silent, total, and unrecoverable after the fact.
    """
    problems = secret_problems()
    if not problems:
        return

    if is_production():
        detail = "\n  - ".join(problems)
        raise RuntimeError(
            "REFUSING TO START — unsafe secret configuration "
            f"(ENVIRONMENT={current_environment()!r}):\n  - {detail}\n\n"
            "Generate strong values and set them in the environment (never in source):\n"
            "  JWT_SECRET:           python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "  FIELD_ENCRYPTION_KEY: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"\n"
            "For local development set ENVIRONMENT=development to downgrade this to a warning."
        )

    import logging
    logging.getLogger(__name__).warning(
        "INSECURE SECRETS (allowed because ENVIRONMENT=%s — this must never be a "
        "production setting): %s", current_environment(), "; ".join(problems))
