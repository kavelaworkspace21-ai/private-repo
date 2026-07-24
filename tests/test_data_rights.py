"""LSAI-LEGAL-05 — DPDP data-rights request tracker (create / list / admin triage / isolation)."""
from tests.conftest import register_and_login, auth


def _register(client, email, role="advocate"):
    r = client.post("/api/auth/register", json={
        "full_name": "T", "email": email, "password": "Sup3rSecret!", "role": role})
    assert r.status_code == 201, r.text
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


def test_create_and_list_own_request(client):
    tok = register_and_login(client, "dr1@firm.com")
    r = client.post("/api/data-rights/", headers=auth(tok),
                    json={"request_type": "correction", "details": "fix my name"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received" and r.json()["deadline"]
    mine = client.get("/api/data-rights/mine", headers=auth(tok)).json()
    assert len(mine) == 1 and mine[0]["request_type"] == "correction"


def test_invalid_request_type_422(client):
    tok = register_and_login(client, "dr2@firm.com")
    assert client.post("/api/data-rights/", headers=auth(tok),
                       json={"request_type": "nonsense"}).status_code == 422


def test_create_requires_auth(client):
    assert client.post("/api/data-rights/", json={"request_type": "access"}).status_code == 401


def test_admin_can_list_and_update(client):
    admin = _register(client, "admin@firm.com", role="firm_admin")
    rid = client.post("/api/data-rights/", headers=auth(admin),
                      json={"request_type": "grievance", "details": "x"}).json()["id"]
    lst = client.get("/api/data-rights/", headers=auth(admin)).json()
    assert any(x["id"] == rid for x in lst)
    upd = client.patch(f"/api/data-rights/{rid}", headers=auth(admin),
                       json={"status": "completed", "resolver_note": "done"})
    assert upd.status_code == 200
    assert upd.json()["status"] == "completed" and upd.json()["resolved_at"]


def test_non_admin_cannot_list_all(client):
    tok = register_and_login(client, "dr3@firm.com")   # advocate, not firm_admin
    assert client.get("/api/data-rights/", headers=auth(tok)).status_code == 403


def test_cross_tenant_update_denied(client):
    a_admin = _register(client, "a-admin@firm.com", role="firm_admin")
    rid = client.post("/api/data-rights/", headers=auth(a_admin),
                      json={"request_type": "access"}).json()["id"]
    b_admin = _register(client, "b-admin@firm.com", role="firm_admin")
    assert client.patch(f"/api/data-rights/{rid}", headers=auth(b_admin),
                        json={"status": "completed"}).status_code == 404
