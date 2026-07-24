"""
Phase C — member consent-on-first-login (DPDP).
Invited members have no consent until they accept; self-registered users already consented.
"""
from tests.conftest import register_and_login, auth


def _admin(client, email="cgadmin@firm.com"):
    client.post("/api/auth/register", json={
        "full_name": "Admin", "email": email, "password": "Sup3rSecret!", "role": "firm_admin"})
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


def test_self_registered_user_does_not_need_consent(client):
    tok = register_and_login(client, "selfreg@firm.com")    # consent captured at registration
    assert client.get("/api/auth/needs-consent", headers=auth(tok)).json()["needs"] is False


def test_invited_member_needs_then_gives_consent(client):
    admin = _admin(client, "cg@firm.com")
    tok = client.post("/api/firm/members", headers=auth(admin),
                      json={"full_name": "New Assoc", "email": "newassoc@firm.com",
                            "role": "associate"}).json()["dev_invite_token"]
    client.post("/api/auth/reset-password", json={"token": tok, "new_password": "AssocPass123"})
    member = client.post("/api/auth/login",
                         json={"email": "newassoc@firm.com", "password": "AssocPass123"}).json()["access_token"]

    # invited member has NOT consented yet
    assert client.get("/api/auth/needs-consent", headers=auth(member)).json()["needs"] is True
    # they accept
    assert client.post("/api/auth/consent", headers=auth(member)).status_code == 200
    # now satisfied
    assert client.get("/api/auth/needs-consent", headers=auth(member)).json()["needs"] is False
    assert any(c["type"] == "privacy_policy" for c in
               client.get("/api/auth/consents", headers=auth(member)).json())


def test_needs_consent_requires_auth(client):
    assert client.get("/api/auth/needs-consent").status_code == 401
