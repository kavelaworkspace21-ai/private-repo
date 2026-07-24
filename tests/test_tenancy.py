"""
Tenant isolation tests (CLAUDE.md section 2.8 / 7.10).
Cross-tenant access is a P0 bug — these tests must FAIL if isolation breaks.
"""
from tests.conftest import register_and_login, auth


def _make_client_and_case(client, token):
    r = client.post("/api/clients/", headers=auth(token),
                    json={"full_name": "Ramesh Kumar", "email": "ramesh@example.com"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = client.post("/api/cases/", headers=auth(token),
                    json={"title": "Ramesh v. State", "client_id": cid, "status": "open"})
    assert r.status_code == 201, r.text
    return cid, r.json()["id"]


# ── Auth is required ────────────────────────────────────────────────────────────
def test_cases_require_auth(client):
    assert client.get("/api/cases/").status_code == 401
    assert client.get("/api/clients/").status_code == 401


# ── Each tenant sees only its own data ──────────────────────────────────────────
def test_list_is_tenant_scoped(client):
    t1 = register_and_login(client, "firm1@example.com", "Firm One")
    t2 = register_and_login(client, "firm2@example.com", "Firm Two")

    _make_client_and_case(client, t1)

    # Firm One sees its case; Firm Two sees nothing
    assert len(client.get("/api/cases/", headers=auth(t1)).json()) == 1
    assert client.get("/api/cases/", headers=auth(t2)).json() == []
    assert len(client.get("/api/clients/", headers=auth(t1)).json()) == 1
    assert client.get("/api/clients/", headers=auth(t2)).json() == []


# ── Cross-tenant direct access is denied (404, no info leak) ─────────────────────
def test_cross_tenant_read_denied(client):
    t1 = register_and_login(client, "firmA@example.com", "Firm A")
    t2 = register_and_login(client, "firmB@example.com", "Firm B")
    cid, case_id = _make_client_and_case(client, t1)

    assert client.get(f"/api/cases/{case_id}", headers=auth(t1)).status_code == 200
    assert client.get(f"/api/cases/{case_id}", headers=auth(t2)).status_code == 404
    assert client.get(f"/api/clients/{cid}", headers=auth(t2)).status_code == 404


def test_cross_tenant_mutation_denied(client):
    t1 = register_and_login(client, "firmX@example.com", "Firm X")
    t2 = register_and_login(client, "firmY@example.com", "Firm Y")
    _cid, case_id = _make_client_and_case(client, t1)

    # Firm Y cannot patch or delete Firm X's case
    assert client.patch(f"/api/cases/{case_id}", headers=auth(t2),
                        json={"title": "hacked"}).status_code == 404
    assert client.delete(f"/api/cases/{case_id}", headers=auth(t2)).status_code == 404
    # Firm X's case is untouched
    assert client.get(f"/api/cases/{case_id}", headers=auth(t1)).json()["title"] == "Ramesh v. State"


def test_cannot_link_case_to_foreign_client(client):
    t1 = register_and_login(client, "f1@example.com", "F1")
    t2 = register_and_login(client, "f2@example.com", "F2")
    cid, _case = _make_client_and_case(client, t1)

    # Firm Two tries to create a case pointing at Firm One's client -> denied
    r = client.post("/api/cases/", headers=auth(t2),
                    json={"title": "sneaky", "client_id": cid, "status": "open"})
    assert r.status_code == 404


def test_diary_today_is_tenant_scoped(client):
    t1 = register_and_login(client, "d1@example.com", "D1")
    t2 = register_and_login(client, "d2@example.com", "D2")
    _cid, case_id = _make_client_and_case(client, t1)

    # Both tenants' dashboards work and Firm Two sees no hearings from Firm One
    r2 = client.get("/api/diary/today", headers=auth(t2))
    assert r2.status_code == 200
    assert r2.json()["today"] == [] and r2.json()["upcoming"] == []
