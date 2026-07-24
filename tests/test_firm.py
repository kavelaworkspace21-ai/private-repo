"""
Phase C — firm workspaces & member roles.
Firm admin invites members into their tenant; members share the tenant; guards hold.
"""
from tests.conftest import register_and_login, auth


def _admin(client, email="firmadmin@firm.com"):
    client.post("/api/auth/register", json={
        "full_name": "Firm Admin", "email": email, "password": "Sup3rSecret!", "role": "firm_admin"})
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


def test_invite_member_and_set_password_then_login(client):
    admin = _admin(client, "a@firm.com")
    r = client.post("/api/firm/members", headers=auth(admin),
                    json={"full_name": "Junior Assoc", "email": "junior@firm.com", "role": "associate"})
    assert r.status_code == 201, r.text
    token = r.json()["dev_invite_token"]          # no SMTP in tests
    # member sets their own password via the invite (reset) token
    assert client.post("/api/auth/reset-password",
                       json={"token": token, "new_password": "MemberPass123"}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"email": "junior@firm.com", "password": "MemberPass123"}).status_code == 200


def test_members_share_the_tenant(client):
    admin = _admin(client, "share@firm.com")
    # admin creates a case
    cid = client.post("/api/clients/", headers=auth(admin),
                      json={"full_name": "C", "email": "c@e.com"}).json()["id"]
    client.post("/api/cases/", headers=auth(admin),
                json={"title": "Firm Case", "client_id": cid, "status": "open"})
    # invite an advocate member, set password, log in
    tok = client.post("/api/firm/members", headers=auth(admin),
                      json={"full_name": "Adv Two", "email": "adv2@firm.com", "role": "advocate"}).json()["dev_invite_token"]
    client.post("/api/auth/reset-password", json={"token": tok, "new_password": "AdvTwoPass123"})
    member = client.post("/api/auth/login",
                         json={"email": "adv2@firm.com", "password": "AdvTwoPass123"}).json()["access_token"]
    # member sees the firm's case (shared tenant)
    cases = client.get("/api/cases/", headers=auth(member)).json()
    assert any(c["title"] == "Firm Case" for c in cases)


def test_list_members_requires_admin(client):
    adv = register_and_login(client, "plain@firm.com")     # advocate, not admin
    assert client.get("/api/firm/members", headers=auth(adv)).status_code == 403


def test_clerk_member_is_read_only(client):
    admin = _admin(client, "ro@firm.com")
    tok = client.post("/api/firm/members", headers=auth(admin),
                      json={"full_name": "Clerk", "email": "clerk@firm.com", "role": "clerk"}).json()["dev_invite_token"]
    client.post("/api/auth/reset-password", json={"token": tok, "new_password": "ClerkPass123"})
    clerk = client.post("/api/auth/login",
                        json={"email": "clerk@firm.com", "password": "ClerkPass123"}).json()["access_token"]
    # clerk can read but not write
    assert client.get("/api/cases/", headers=auth(clerk)).status_code == 200
    assert client.post("/api/clients/", headers=auth(clerk),
                       json={"full_name": "X", "email": "x@e.com"}).status_code == 403


def test_cannot_remove_last_admin(client):
    admin = _admin(client, "solo@firm.com")
    me = client.get("/api/auth/me", headers=auth(admin)).json()
    # demote self (last admin) → blocked
    r = client.patch(f"/api/firm/members/{me['id']}", headers=auth(admin), json={"role": "advocate"})
    assert r.status_code == 400


def test_members_are_tenant_isolated(client):
    a = _admin(client, "fa@firm.com")
    b = _admin(client, "fb@firm.com")
    client.post("/api/firm/members", headers=auth(a),
                json={"full_name": "A Member", "email": "amem@firm.com", "role": "associate"})
    # B's member list must not include A's member
    emails_b = {m["email"] for m in client.get("/api/firm/members", headers=auth(b)).json()}
    assert "amem@firm.com" not in emails_b
