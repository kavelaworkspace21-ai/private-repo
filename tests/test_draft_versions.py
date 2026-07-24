"""
Phase C — draft versioning. Saving creates v1; editing creates a new version and re-opens the
draft for review (an edited approved draft is no longer 'final'); revert restores a version.
"""
from tests.conftest import register_and_login, auth
from app.ai.safety import DRAFT_STATUS_REVIEW, DRAFT_STATUS_APPROVED


def _save(client, tok, content="IN THE COURT ...\n\nApplication v1."):
    return client.post("/api/drafts/", headers=auth(tok), json={
        "document_type": "regular_bail", "title": "Bail", "content": content}).json()


def test_save_creates_version_one(client):
    t = register_and_login(client, "dv1@firm.com")
    did = _save(client, t)["id"]
    versions = client.get(f"/api/drafts/{did}/versions", headers=auth(t)).json()
    assert len(versions) == 1 and versions[0]["version_no"] == 1


def test_edit_adds_version_and_reopens_review(client):
    t = register_and_login(client, "dv2@firm.com")
    did = _save(client, t)["id"]
    # approve it first
    assert client.post(f"/api/drafts/{did}/approve", headers=auth(t)).json()["status"] == DRAFT_STATUS_APPROVED
    # edit → new version + status back to review
    r = client.patch(f"/api/drafts/{did}", headers=auth(t), json={"content": "Edited body v2."})
    assert r.status_code == 200
    assert r.json()["status"] == DRAFT_STATUS_REVIEW
    assert r.json()["approved_by"] is None
    versions = client.get(f"/api/drafts/{did}/versions", headers=auth(t)).json()
    assert len(versions) == 2 and versions[0]["version_no"] == 2


def test_revert_restores_previous_version(client):
    t = register_and_login(client, "dv3@firm.com")
    did = _save(client, t, content="Original v1 text.")["id"]
    client.patch(f"/api/drafts/{did}", headers=auth(t), json={"content": "Replaced v2 text."})
    # revert to v1
    r = client.post(f"/api/drafts/{did}/revert/1", headers=auth(t))
    assert r.status_code == 200
    assert "Original v1 text." in r.json()["content"]
    # revert created v3
    assert len(client.get(f"/api/drafts/{did}/versions", headers=auth(t)).json()) == 3


def test_versions_tenant_isolated(client):
    owner = register_and_login(client, "dvowner@firm.com")
    did = _save(client, owner)["id"]
    intruder = register_and_login(client, "dvintruder@firm.com")
    assert client.get(f"/api/drafts/{did}/versions", headers=auth(intruder)).status_code == 404
    assert client.patch(f"/api/drafts/{did}", headers=auth(intruder),
                        json={"content": "hack"}).status_code == 404


def test_versions_response_includes_content(client):
    """The version-history UI renders each version's full text from this response."""
    t = register_and_login(client, "dvcontent@firm.com")
    did = _save(client, t, content="Unique body marker XYZ.")["id"]
    versions = client.get(f"/api/drafts/{did}/versions", headers=auth(t)).json()
    assert "content" in versions[0]
    assert "Unique body marker XYZ." in versions[0]["content"]


def test_revert_tenant_isolated(client):
    owner = register_and_login(client, "dvrevowner@firm.com")
    did = _save(client, owner)["id"]
    client.patch(f"/api/drafts/{did}", headers=auth(owner), json={"content": "Replaced v2."})
    intruder = register_and_login(client, "dvrevintruder@firm.com")
    assert client.post(f"/api/drafts/{did}/revert/1", headers=auth(intruder)).status_code == 404


def test_same_tenant_clerk_can_view_versions_but_not_revert(client):
    """Read-only clerk (same firm) may view history but the UI's Revert is blocked server-side."""
    client.post("/api/auth/register", json={
        "full_name": "Firm Admin", "email": "dvadmin@firm.com",
        "password": "Sup3rSecret!", "role": "firm_admin"})
    admin = client.post("/api/auth/login",
                        json={"email": "dvadmin@firm.com", "password": "Sup3rSecret!"}).json()["access_token"]
    did = _save(client, admin)["id"]
    client.patch(f"/api/drafts/{did}", headers=auth(admin), json={"content": "Admin v2 body."})
    tok = client.post("/api/firm/members", headers=auth(admin),
                      json={"full_name": "Clerk", "email": "dvclerk@firm.com", "role": "clerk"}).json()["dev_invite_token"]
    client.post("/api/auth/reset-password", json={"token": tok, "new_password": "ClerkPass123"})
    clerk = client.post("/api/auth/login",
                        json={"email": "dvclerk@firm.com", "password": "ClerkPass123"}).json()["access_token"]
    # read allowed
    r = client.get(f"/api/drafts/{did}/versions", headers=auth(clerk))
    assert r.status_code == 200 and len(r.json()) == 2
    # write (revert) blocked for read-only role
    assert client.post(f"/api/drafts/{did}/revert/1", headers=auth(clerk)).status_code == 403
