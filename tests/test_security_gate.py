"""The secret sanity gate must refuse to boot on unsafe signing material.

The vulnerability it closes: `JWT_SECRET` defaulted to the placeholder
"change-me-in-production" published in app/auth/config.py. Unset in production, the app
booted normally and signed every token with a string any reader of the repo knows —
total authentication bypass, silently. `FIELD_ENCRYPTION_KEY` compounds it, because
crypto.py derives the at-rest key from JWT_SECRET when it is unset.
"""
import pytest

from app.security_gate import (MIN_JWT_SECRET_LEN, PLACEHOLDER_JWT_SECRET,
                               assert_secrets_sane, current_environment, is_production,
                               secret_problems)

STRONG_JWT = "a" * 64
STRONG_FERNET = "TZzUR3xVxK1p9m2n4b6v8c0X2z4A6s8D0f2G4h6J8k0="


def _env(monkeypatch, *, environment=None, jwt=STRONG_JWT, fernet=STRONG_FERNET):
    if environment is None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT", environment)
    for name, val in (("JWT_SECRET", jwt), ("FIELD_ENCRYPTION_KEY", fernet)):
        if val is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, val)


# ── Fails closed ────────────────────────────────────────────────────────────────
def test_unset_environment_is_treated_as_production(monkeypatch):
    """Forgetting ENVIRONMENT must not silently grant the permissive path."""
    _env(monkeypatch, environment=None)
    assert current_environment() == "production"
    assert is_production() is True


def test_placeholder_jwt_secret_blocks_boot_in_production(monkeypatch):
    _env(monkeypatch, environment="production", jwt=PLACEHOLDER_JWT_SECRET)
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        assert_secrets_sane()


def test_missing_jwt_secret_blocks_boot_in_production(monkeypatch):
    _env(monkeypatch, environment="production", jwt=None)
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        assert_secrets_sane()


def test_short_jwt_secret_blocks_boot(monkeypatch):
    _env(monkeypatch, environment="production", jwt="x" * (MIN_JWT_SECRET_LEN - 1))
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        assert_secrets_sane()


def test_missing_field_encryption_key_blocks_boot(monkeypatch):
    """Unset, crypto.py derives the at-rest key from JWT_SECRET — TOTP secrets then share
    the signing key's fate instead of being independently protected."""
    _env(monkeypatch, environment="production", fernet=None)
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        assert_secrets_sane()


def test_an_unrecognised_environment_name_is_treated_as_production(monkeypatch):
    """"staging", "prod-eu", a typo — anything not explicitly non-production fails closed."""
    _env(monkeypatch, environment="staging", jwt=PLACEHOLDER_JWT_SECRET)
    with pytest.raises(RuntimeError):
        assert_secrets_sane()


# ── Permits legitimate development ──────────────────────────────────────────────
@pytest.mark.parametrize("env_name", ["development", "dev", "local", "test", "testing", "ci"])
def test_development_environments_warn_instead_of_blocking(monkeypatch, env_name):
    _env(monkeypatch, environment=env_name, jwt=PLACEHOLDER_JWT_SECRET, fernet=None)
    assert_secrets_sane()          # must not raise
    assert is_production() is False


def test_strong_secrets_pass_in_production(monkeypatch):
    _env(monkeypatch, environment="production")
    assert secret_problems() == []
    # The boot gate also checks the database, so a production run needs a real one; the
    # developer's ambient DATABASE_URL points at SQLite.
    monkeypatch.setenv("DATABASE_URL",
                       "postgresql+psycopg://u:p@host:5432/db?sslmode=require")
    assert_secrets_sane()


# ── Never leaks the value it is guarding ────────────────────────────────────────
def test_problem_messages_never_contain_the_secret_value(monkeypatch):
    secret = "SuperSecretValue" + "z" * 40
    _env(monkeypatch, environment="production", jwt=secret[:8], fernet=None)  # too short
    blob = " ".join(secret_problems())
    assert secret[:8] not in blob, "the gate echoed the secret value into its message"
    assert "JWT_SECRET" in blob and "FIELD_ENCRYPTION_KEY" in blob


def test_the_raised_error_names_problems_but_not_values(monkeypatch):
    _env(monkeypatch, environment="production", jwt="shortsecret", fernet=None)
    with pytest.raises(RuntimeError) as exc:
        assert_secrets_sane()
    assert "shortsecret" not in str(exc.value)


def test_boot_gate_checks_the_database_as_well_as_the_secrets(monkeypatch):
    """The gate composes secret_problems() + database_problems().

    An earlier version folded the database checks INTO secret_problems(), so a function
    named "secret problems" reported database configuration. Each function now reports
    what its name says and the gate combines them — this pins that composition, since
    dropping either half would silently narrow the gate.
    """
    _env(monkeypatch, environment="production")            # strong secrets
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./legal_server.db")
    assert secret_problems() == [], "database config must not leak into secret_problems()"
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        assert_secrets_sane()                              # ...but the gate still refuses


def test_gate_passes_with_strong_secrets_and_a_tls_database(monkeypatch):
    _env(monkeypatch, environment="production")
    monkeypatch.setenv("DATABASE_URL",
                       "postgresql+psycopg://u:p@host:5432/db?sslmode=require")
    assert_secrets_sane()
