"""Health / readiness / ops-status endpoints.

/healthz = liveness (soul + DB), /readyz = readiness (vector index built), /api/admin/status =
protected operational identity with NO secret values.
"""
from tests.conftest import register_and_login, auth


def _firm_admin(client, email):
    client.post("/api/auth/register", json={
        "full_name": "Firm Admin", "email": email, "password": "Sup3rSecret!", "role": "firm_admin"})
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


def test_health_reports_version_and_soul(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.2.0" and body["soul"] == "intact"


def test_healthz_liveness_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["db"] == "ok" and body["soul"] == "intact"


def test_readyz_ready_when_index_present(client, monkeypatch):
    import app.ops.release as rel
    monkeypatch.setattr(rel, "_chroma_count", lambda: 8646)
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready" and body["vector_index"]["ok"] is True


def test_readyz_not_ready_when_index_missing(client, monkeypatch):
    import app.ops.release as rel
    monkeypatch.setattr(rel, "_chroma_count", lambda: None)   # index not built
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"


def test_admin_status_requires_firm_admin(client):
    adv = register_and_login(client, "adv-status@firm.com")   # advocate, not firm admin
    assert client.get("/api/admin/status", headers=auth(adv)).status_code == 403


def test_admin_status_returns_identity_without_secrets(client):
    admin = _firm_admin(client, "admin-status@firm.com")
    r = client.get("/api/admin/status", headers=auth(admin))
    assert r.status_code == 200
    body = r.json()
    assert body["app_version"] == "0.2.0"
    assert body["corpus_fingerprint"] == "2965aab084ff"
    # config is presence-only booleans, never values
    assert set(body["config"].values()) <= {True, False}
