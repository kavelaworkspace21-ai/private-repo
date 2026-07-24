"""LSAI-LEGAL-07 — advocate/firm verification + founder approval + AI access gate."""
from tests.conftest import register_and_login, auth

TOKEN = "founder-secret-token"
FOUNDER = {"X-Admin-Token": TOKEN}


def _register(client, email, role="firm_admin"):
    r = client.post("/api/auth/register", json={
        "full_name": "T", "email": email, "password": "Sup3rSecret!", "role": role})
    assert r.status_code == 201, r.text
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


def test_default_status_pending(client):
    tok = _register(client, "v1@firm.com")
    assert client.get("/api/firm/verification", headers=auth(tok)).json()["status"] == "pending"


def test_submit_records_jurisdiction(client):
    tok = _register(client, "v2@firm.com")
    r = client.post("/api/firm/verification", headers=auth(tok),
                    json={"jurisdiction": "Maharashtra", "bar_enrolment": "MAH/1234/2015"})
    assert r.status_code == 200
    assert r.json()["jurisdiction"] == "Maharashtra" and r.json()["status"] == "pending"


def test_non_admin_cannot_submit(client):
    tok = register_and_login(client, "v3@firm.com")   # advocate, not firm_admin
    assert client.post("/api/firm/verification", headers=auth(tok),
                       json={"jurisdiction": "X"}).status_code == 403


def test_founder_can_verify(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    tok = _register(client, "v4@firm.com")
    pend = client.get("/api/admin/pending-verifications", headers=FOUNDER).json()
    assert pend and pend[0]["status"] == "pending"
    tid = pend[0]["tenant_id"]
    r = client.patch(f"/api/admin/verify/{tid}", headers=FOUNDER,
                     json={"status": "verified", "note": "checked enrolment"})
    assert r.status_code == 200 and r.json()["status"] == "verified" and r.json()["verified_at"]
    assert client.get("/api/firm/verification", headers=auth(tok)).json()["status"] == "verified"


def test_founder_endpoints_require_token(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    assert client.get("/api/admin/pending-verifications").status_code == 403
    assert client.get("/api/admin/pending-verifications",
                      headers={"X-Admin-Token": "wrong"}).status_code == 403


def test_founder_denied_when_admin_token_unset(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert client.get("/api/admin/pending-verifications", headers=FOUNDER).status_code == 403


def test_ai_gate_blocks_unverified_when_enabled(client, monkeypatch):
    monkeypatch.setenv("AI_REQUIRES_VERIFICATION", "1")
    tok = register_and_login(client, "v5@firm.com")   # advocate, tenant pending
    r = client.post("/api/ai/chat", headers=auth(tok), json={"message": "hello"})
    assert r.status_code == 403
