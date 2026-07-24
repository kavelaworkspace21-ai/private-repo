"""
Phase B / DPDP — consent capture + data-principal rights (access, erasure).
Aligns with DPDP Act 2023 and SC draft AI-in-Courts Regs 2026 reg. 10.
"""
from tests.conftest import register_and_login, auth


def _seed(client, tok):
    cid = client.post("/api/clients/", headers=auth(tok),
                      json={"full_name": "Ramesh", "email": "r@e.com"}).json()["id"]
    client.post("/api/cases/", headers=auth(tok),
                json={"title": "Ramesh v. State", "client_id": cid, "status": "open"})


# ── Consent ─────────────────────────────────────────────────────────────────────
def test_registration_records_consent(client):
    tok = register_and_login(client, "consent@firm.com")
    rows = client.get("/api/auth/consents", headers=auth(tok)).json()
    types = {r["type"] for r in rows}
    assert "terms_of_service" in types and "privacy_policy" in types
    assert all(r["granted"] for r in rows)


def test_declining_terms_blocks_registration(client):
    r = client.post("/api/auth/register", json={
        "full_name": "No Consent", "email": "no@firm.com", "password": "Sup3rSecret!",
        "role": "advocate", "accept_terms": False})
    assert r.status_code == 422   # validator rejects accept_terms=False


# ── Right to access / export ─────────────────────────────────────────────────────
def test_export_returns_tenant_data_no_password(client):
    tok = register_and_login(client, "export@firm.com")
    _seed(client, tok)
    data = client.get("/api/account/export", headers=auth(tok)).json()
    assert data["user"]["email"] == "export@firm.com"
    assert "hashed_password" not in data["user"]
    assert len(data["clients"]) == 1 and len(data["cases"]) == 1
    assert any(c["consent_type"] == "privacy_policy" for c in data["consents"])


def test_privacy_statement_says_no_training(client):
    tok = register_and_login(client, "priv@firm.com")
    r = client.get("/api/account/privacy", headers=auth(tok)).json()
    assert "train" in r["no_training"].lower()


# ── Right to erasure ─────────────────────────────────────────────────────────────
def test_erasure_requires_confirm(client):
    tok = register_and_login(client, "del0@firm.com")
    assert client.request("DELETE", "/api/account/", headers=auth(tok),
                          json={"confirm": False}).status_code == 400


def test_account_deletion_removes_data_and_login(client):
    tok = register_and_login(client, "del@firm.com")
    _seed(client, tok)
    r = client.request("DELETE", "/api/account/", headers=auth(tok), json={"confirm": True})
    assert r.status_code == 200 and r.json()["status"] == "deleted"
    # cannot log in anymore
    assert client.post("/api/auth/login",
                       json={"email": "del@firm.com", "password": "Sup3rSecret!"}).status_code == 401


def test_export_requires_auth(client):
    assert client.get("/api/account/export").status_code == 401


# ── Profile (account settings) ──────────────────────────────────────────────────
def test_update_profile(client):
    tok = register_and_login(client, "profedit@firm.com")
    r = client.patch("/api/account/profile", headers=auth(tok),
                     json={"full_name": "Adv. New Name", "phone": "+91 90000 11111"})
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Adv. New Name"
    assert r.json()["phone"] == "+91 90000 11111"
    me = client.get("/api/auth/me", headers=auth(tok)).json()
    assert me["full_name"] == "Adv. New Name" and me["phone"] == "+91 90000 11111"


def test_update_profile_requires_auth(client):
    assert client.patch("/api/account/profile", json={"full_name": "X"}).status_code == 401


# ── LSAI-LEGAL-03: consent precision / provable receipts ─────────────────────────
def test_consent_receipt_records_source(client):
    tok = register_and_login(client, "receipt@firm.com")
    rows = client.get("/api/auth/consents", headers=auth(tok)).json()
    assert rows and all(r["source"] == "registration" for r in rows)


def test_needs_consent_reports_versions(client):
    tok = register_and_login(client, "ver@firm.com")
    v = client.get("/api/auth/needs-consent", headers=auth(tok)).json()
    assert v["needs"] is False          # just registered at current versions
    assert v["terms_version"] and v["privacy_version"] and v["notice_version"]


def test_consent_page_post_records_consent_page_source(client):
    tok = register_and_login(client, "page@firm.com")
    client.post("/api/auth/consent", headers=auth(tok), json={})
    rows = client.get("/api/auth/consents", headers=auth(tok)).json()
    assert any(r["source"] == "consent_page" for r in rows)
