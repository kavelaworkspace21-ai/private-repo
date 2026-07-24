"""Production observability — request-id correlation + guarded Sentry."""
from app.observability import init_sentry, get_request_id


def test_response_has_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid and rid != "-"


def test_incoming_request_id_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers.get("X-Request-ID") == "trace-abc-123"


def test_sentry_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False


def test_request_id_default_outside_request():
    assert get_request_id() == "-"
