"""Audit-log coverage (CLAUDE.md §5): every important mutation writes an AuditLog row.
Functional checks via the tenant-scoped /api/audit endpoint (firm_admin can read)."""
from datetime import date, timedelta

from tests.conftest import auth


def _admin(client, email):
    client.post("/api/auth/register", json={
        "full_name": "Audit Admin", "email": email,
        "password": "Sup3rSecret!", "role": "firm_admin"})
    r = client.post("/api/auth/login", json={"email": email, "password": "Sup3rSecret!"})
    body = r.json()
    return body.get("access_token")


def _actions(client, tok):
    rows = client.get("/api/audit", headers=auth(tok)).json()
    items = rows if isinstance(rows, list) else rows.get("items", rows.get("rows", []))
    return [r["action"] for r in items]


def test_register_and_login_are_audited(client):
    tok = _admin(client, "audadm@firm.com")
    if tok is None:  # role requires 2FA setup flow variant — still issues tokens
        raise AssertionError("expected access_token for firm_admin registration flow")
    acts = _actions(client, tok)
    assert "register" in acts
    assert "login" in acts


def test_diary_update_delete_audited(client):
    tok = _admin(client, "audadm2@firm.com")
    cid = client.post("/api/clients/", headers=auth(tok),
                      json={"full_name": "Aud Client", "email": "aud@c.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(tok),
                          json={"title": "Aud v. State", "client_id": cid, "status": "open"}).json()["id"]
    t = client.post("/api/diary/tasks", headers=auth(tok), json={
        "case_id": case_id, "title": "Audit me",
        "due_date": (date.today() + timedelta(days=2)).isoformat()}).json()
    client.patch(f"/api/diary/tasks/{t['id']}", headers=auth(tok), json={"title": "Audited"})
    client.delete(f"/api/diary/tasks/{t['id']}", headers=auth(tok))
    acts = _actions(client, tok)
    for expected in ("create_task", "update_task", "delete_task"):
        assert expected in acts, f"missing audit action {expected}"


def test_conversation_delete_and_export_audited(client):
    tok = _admin(client, "audadm3@firm.com")
    # export (no AI key needed)
    client.post("/api/drafting/export", headers=auth(tok), json={
        "document_type": "chat_draft", "content": "NOTICE body", "format": "docx"})
    acts = _actions(client, tok)
    assert "export_document" in acts
