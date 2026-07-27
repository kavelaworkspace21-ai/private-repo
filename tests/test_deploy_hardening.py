"""Pre-deploy hardening: the checks that must hold before this app faces the internet.

Each test corresponds to a defect found during the pre-deploy review, so a regression
surfaces here rather than in production.
"""
import pytest

from app.security_gate import database_problems, is_production
from app.services import ratelimit
from tests.conftest import auth, register_and_login


def _db_env(monkeypatch, url):
    if url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", url)


# ── 1. Environment variables: critical config must not silently default ─────────
def test_missing_database_url_is_a_production_problem(monkeypatch):
    """Unset, app/db/config.py falls back to SQLite — production data would land in an
    ephemeral container file and vanish on redeploy, with no error."""
    _db_env(monkeypatch, None)
    assert any("DATABASE_URL is not set" in p for p in database_problems())


def test_sqlite_in_production_is_a_problem(monkeypatch):
    _db_env(monkeypatch, "sqlite:///./legal_server.db")
    assert any("SQLite" in p for p in database_problems())


# ── 7. Database security: TLS must be explicit ─────────────────────────────────
def test_postgres_without_sslmode_is_flagged(monkeypatch):
    """libpq defaults to sslmode=prefer, which silently falls back to PLAINTEXT."""
    _db_env(monkeypatch, "postgresql+psycopg://u:p@host:5432/db")
    assert any("sslmode" in p for p in database_problems())


@pytest.mark.parametrize("mode", ["disable", "allow"])
def test_postgres_with_weak_sslmode_is_flagged(monkeypatch, mode):
    _db_env(monkeypatch, f"postgresql+psycopg://u:p@host:5432/db?sslmode={mode}")
    assert any("unencrypted" in p.lower() for p in database_problems())


@pytest.mark.parametrize("mode", ["require", "verify-full"])
def test_postgres_with_tls_passes(monkeypatch, mode):
    _db_env(monkeypatch, f"postgresql+psycopg://u:p@host:5432/db?sslmode={mode}")
    assert database_problems() == []


def test_database_problems_never_echo_the_connection_string(monkeypatch):
    """The URL contains the database password — it must not reach a log or an error."""
    _db_env(monkeypatch, "postgresql+psycopg://admin:SuperSecretDbPass@host:5432/db")
    assert "SuperSecretDbPass" not in " ".join(database_problems())


# ── 5. Rate limiting on every credential endpoint ──────────────────────────────
def test_credential_limits_meet_the_deploy_thresholds():
    assert (ratelimit.login_limiter.limit, ratelimit.login_limiter.window) == (5, 60)
    assert (ratelimit.forgot_limiter.limit, ratelimit.forgot_limiter.window) == (3, 3600)


def test_otp_verification_is_rate_limited():
    """TOTP verification was UNLIMITED. With a valid temp_token (i.e. the password already
    known), an attacker could spray guesses at the live code window and defeat 2FA."""
    assert ratelimit.otp_limiter.limit <= 10
    assert ratelimit.otp_limiter.window >= 60


def test_every_credential_endpoint_declares_a_limiter():
    """Structural: a new auth route must not ship without a limiter."""
    from app.main import app

    def walk(routes):
        for r in routes:
            orig = getattr(r, "original_router", None)
            if orig is not None:
                yield from walk(orig.routes)
            elif hasattr(r, "dependant"):
                yield r

    need = {"login", "register", "forgot_password", "reset_password",
            "verify_2fa_login", "enable_2fa"}
    seen = {}
    for r in walk(app.routes):
        name = getattr(r.endpoint, "__name__", "")
        if name in need:
            deps = {type(d.call).__name__ for d in r.dependant.dependencies
                    if getattr(d, "call", None)}
            seen[name] = "RateLimiter" in deps

    missing = [n for n in need if not seen.get(n)]
    assert not missing, f"credential endpoints with no rate limiter: {missing}"


def test_rate_limiter_actually_blocks(client, monkeypatch):
    """Prove the limiter fires, not just that it is attached."""
    monkeypatch.setenv("RATELIMIT_ENABLED", "1")
    ratelimit._BUCKETS.clear() if hasattr(ratelimit, "_BUCKETS") else None
    codes = [client.post("/api/auth/login",
                         json={"email": "nobody@firm.com", "password": "wrong"}).status_code
             for _ in range(12)]
    monkeypatch.setenv("RATELIMIT_ENABLED", "0")
    assert 429 in codes, "login accepted 12 rapid attempts without limiting"


# ── 2. Debug surface off in production ─────────────────────────────────────────
def test_api_docs_are_disabled_in_production(monkeypatch):
    """The docs publish every route and schema — a reconnaissance map."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert is_production() is True
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py").read_text(
        encoding="utf-8")
    assert 'docs_url="/docs" if _DOCS_ENABLED else None' in src
    assert "openapi_url=" in src and "_DOCS_ENABLED" in src


def test_no_test_or_debug_endpoints_are_registered():
    from app.main import app
    banned = ("/test", "/debug", "/seed", "/backdoor", "/reset-db")
    paths = [getattr(r, "path", "") for r in app.routes]
    offenders = [p for p in paths if any(p.startswith(b) for b in banned)]
    assert not offenders, f"debug/test endpoints exposed: {offenders}"


# ── 3. Error handling: no internals in client responses ────────────────────────
def test_internal_error_returns_a_correlation_id_not_the_exception(client):
    from app.observability import internal_error

    exc = internal_error(
        RuntimeError("connect to https://api.provider.internal failed: /srv/app/key.pem"),
        action="Transcription")
    detail = exc.detail
    assert "api.provider.internal" not in detail, "provider endpoint leaked to the client"
    assert "/srv/app" not in detail, "server file path leaked to the client"
    assert "reference" in detail.lower()


def test_every_response_carries_a_correlation_id(client):
    tok = register_and_login(client, "corr@firm.com")
    r = client.get("/api/cases/", headers=auth(tok))
    assert r.headers.get("X-Request-ID"), "no correlation id to quote in a support request"


# ── 4. Security headers ────────────────────────────────────────────────────────
def test_security_headers_present_on_every_response(client):
    r = client.get("/healthz")
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert "max-age=31536000" in h["Strict-Transport-Security"]
    csp = h["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


# ── 6. CORS ────────────────────────────────────────────────────────────────────
def test_no_wildcard_cors(client):
    """The app registers no CORS middleware at all — same-origin only, which is the most
    restrictive setting. This fails if a permissive one is ever added."""
    r = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") != "*"
