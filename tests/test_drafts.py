"""
Draft review/approval workflow tests (CLAUDE.md section 2.4):
a draft is never 'final' without an explicit advocate approval.
"""
from tests.conftest import register_and_login, auth
from app.ai.safety import DRAFT_STATUS_REVIEW, DRAFT_STATUS_APPROVED, DRAFT_DISCLAIMER


def _save(client, token, content="IN THE COURT OF ...\n\nApplication."):
    return client.post("/api/drafts/", headers=auth(token), json={
        "document_type": "regular_bail", "title": "Bail — Ramesh", "content": content,
    })


def test_saved_draft_starts_in_review(client):
    t = register_and_login(client, "d1@firm.com")
    r = _save(client, t)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == DRAFT_STATUS_REVIEW
    assert body["approved_by"] is None


def test_disclaimer_is_enforced_on_save(client):
    t = register_and_login(client, "d2@firm.com")
    r = _save(client, t, content="Body without disclaimer.")
    assert DRAFT_DISCLAIMER.split(".")[0] in r.json()["content"]


def test_approve_requires_explicit_action(client):
    t = register_and_login(client, "d3@firm.com")
    draft_id = _save(client, t).json()["id"]
    r = client.post(f"/api/drafts/{draft_id}/approve", headers=auth(t))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == DRAFT_STATUS_APPROVED
    assert body["approved_by"] is not None
    assert body["approved_at"] is not None


def test_clerk_cannot_save_or_approve(client):
    # advocate creates a draft
    adv = register_and_login(client, "adv@firm.com")
    draft_id = _save(client, adv).json()["id"]
    # clerk in a DIFFERENT tenant can't even see it; clerk in SAME tenant can't approve
    client.post("/api/auth/register", json={
        "full_name": "Clerk", "email": "clerk2@firm.com",
        "password": "Sup3rSecret!", "role": "clerk"})
    r = client.post("/api/auth/login", json={"email": "clerk2@firm.com", "password": "Sup3rSecret!"})
    clerk = r.json()["access_token"]
    assert _save(client, clerk).status_code == 403
    assert client.post(f"/api/drafts/{draft_id}/approve", headers=auth(clerk)).status_code in (403, 404)


def test_chat_draft_flows_into_review_queue(client):
    """Documents drafted in the CHAT save into the same review queue: review status,
    listed, approvable, and exportable to DOCX — one loop for both drafting surfaces."""
    adv = register_and_login(client, "chatdraft@firm.com")
    r = client.post("/api/drafts/", headers=auth(adv), json={
        "document_type": "chat_draft",
        "title": "Cheque Dishonour Notice (s.138 NI Act) — chat",
        "content": "LEGAL NOTICE\n\nUnder s.138 NI Act ... pay within 15 days.\n\nDraft for advocate review.",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == DRAFT_STATUS_REVIEW
    ids = [d["id"] for d in client.get("/api/drafts/", headers=auth(adv)).json()]
    assert body["id"] in ids
    ap = client.post(f"/api/drafts/{body['id']}/approve", headers=auth(adv))
    assert ap.status_code == 200
    ex = client.post("/api/drafting/export", headers=auth(adv), json={
        "document_type": "chat_draft", "content": "LEGAL NOTICE\n\ntest body", "format": "docx"})
    assert ex.status_code == 200 and ex.content[:2] == b"PK"


def test_chat_draft_links_to_owned_case_only(client):
    """A chat draft may link to one of the advocate's OWN matters; a case id from
    another tenant is rejected (ownership check on save)."""
    adv = register_and_login(client, "linker@firm.com")
    cid = client.post("/api/clients/", headers=auth(adv),
                      json={"full_name": "Link Client", "email": "lc@c.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(adv),
                          json={"title": "Link v. State", "client_id": cid, "status": "open"}).json()["id"]
    r = client.post("/api/drafts/", headers=auth(adv), json={
        "document_type": "chat_draft", "title": "Linked chat draft",
        "content": "NOTICE body. Draft for advocate review.", "case_id": case_id})
    assert r.status_code == 201 and r.json()["case_id"] == case_id

    outsider = register_and_login(client, "linkerb@firm.com")
    r2 = client.post("/api/drafts/", headers=auth(outsider), json={
        "document_type": "chat_draft", "title": "Cross-tenant link attempt",
        "content": "NOTICE body.", "case_id": case_id})
    assert r2.status_code == 404      # someone else's matter → rejected


def test_draft_is_tenant_isolated(client):
    t1 = register_and_login(client, "owner@firm.com")
    t2 = register_and_login(client, "intruder@firm.com")
    draft_id = _save(client, t1).json()["id"]
    assert client.get(f"/api/drafts/{draft_id}", headers=auth(t2)).status_code == 404
    assert client.get("/api/drafts/", headers=auth(t2)).json() == []
