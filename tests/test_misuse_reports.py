"""LSAI-LEGAL-16 — misuse/abuse reporting (create / mine / admin triage / isolation / auth)."""
from tests.conftest import register_and_login, auth


def _register(client, email, role="advocate"):
    r = client.post("/api/auth/register", json={
        "full_name": "T", "email": email, "password": "Sup3rSecret!", "role": role})
    assert r.status_code == 201, r.text
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


def test_create_and_list_own_report(client):
    tok = register_and_login(client, "m1@firm.com")
    r = client.post("/api/misuse/", headers=auth(tok),
                    json={"category": "abuse", "subject": "Spam in shared workspace",
                          "details": "repeated junk"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received" and r.json()["category"] == "abuse"
    mine = client.get("/api/misuse/mine", headers=auth(tok)).json()
    assert len(mine) == 1 and mine[0]["subject"] == "Spam in shared workspace"


def test_invalid_category_422(client):
    tok = register_and_login(client, "m2@firm.com")
    assert client.post("/api/misuse/", headers=auth(tok),
                       json={"category": "nope", "subject": "x"}).status_code == 422


def test_subject_required(client):
    tok = register_and_login(client, "m2b@firm.com")
    assert client.post("/api/misuse/", headers=auth(tok),
                       json={"category": "other", "subject": "   "}).status_code == 422


def test_create_requires_auth(client):
    assert client.post("/api/misuse/", json={"category": "abuse", "subject": "x"}).status_code == 401


def test_admin_can_list_and_update(client):
    admin = _register(client, "m-admin@firm.com", role="firm_admin")
    rid = client.post("/api/misuse/", headers=auth(admin),
                      json={"category": "security", "subject": "possible leak"}).json()["id"]
    assert any(x["id"] == rid for x in client.get("/api/misuse/", headers=auth(admin)).json())
    upd = client.patch(f"/api/misuse/{rid}", headers=auth(admin),
                       json={"status": "actioned", "resolver_note": "handled"})
    assert upd.status_code == 200 and upd.json()["status"] == "actioned" and upd.json()["resolved_at"]


def test_non_admin_cannot_list_all(client):
    tok = register_and_login(client, "m3@firm.com")
    assert client.get("/api/misuse/", headers=auth(tok)).status_code == 403


def test_cross_tenant_update_denied(client):
    a = _register(client, "ma-admin@firm.com", role="firm_admin")
    rid = client.post("/api/misuse/", headers=auth(a),
                      json={"category": "other", "subject": "x"}).json()["id"]
    b = _register(client, "mb-admin@firm.com", role="firm_admin")
    assert client.patch(f"/api/misuse/{rid}", headers=auth(b),
                        json={"status": "dismissed"}).status_code == 404
