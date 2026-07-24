"""Abuse-hardening tests: size caps + type constraints on every write surface.
A request that isn't a plausible legal document/question is rejected at the boundary
(422/400) before it can burn LLM credits, CPU, or storage."""
import io

from tests.conftest import register_and_login, auth


def test_chat_message_size_capped(client):
    t = register_and_login(client, "hard1@firm.com")
    r = client.post("/api/ai/chat", headers=auth(t), json={"message": "x" * 9000})
    assert r.status_code == 422
    r = client.post("/api/ai/chat", headers=auth(t), json={"message": ""})
    assert r.status_code == 422


def test_drafting_fields_bounded(client):
    t = register_and_login(client, "hard2@firm.com")
    # oversized single field
    r = client.post("/api/drafting/generate", headers=auth(t), json={
        "document_type": "affidavit", "fields": {"facts_to_state": "y" * 9000}})
    assert r.status_code == 422
    # too many fields
    r = client.post("/api/drafting/generate", headers=auth(t), json={
        "document_type": "affidavit", "fields": {f"k{i}": "v" for i in range(41)}})
    assert r.status_code == 422


def test_export_content_and_format_capped(client):
    t = register_and_login(client, "hard3@firm.com")
    r = client.post("/api/drafting/export", headers=auth(t), json={
        "document_type": "chat_draft", "content": "z" * 300_001, "format": "docx"})
    assert r.status_code == 422
    r = client.post("/api/drafting/export", headers=auth(t), json={
        "document_type": "chat_draft", "content": "hello", "format": "exe"})
    assert r.status_code == 422


def test_draft_save_caps(client):
    t = register_and_login(client, "hard4@firm.com")
    r = client.post("/api/drafts/", headers=auth(t), json={
        "document_type": "chat_draft", "title": "t" * 400, "content": "body"})
    assert r.status_code == 422
    r = client.post("/api/drafts/", headers=auth(t), json={
        "document_type": "chat_draft", "title": "ok", "content": "c" * 300_001})
    assert r.status_code == 422


def test_upload_rejects_disallowed_extension(client):
    t = register_and_login(client, "hard5@firm.com")
    cid = client.post("/api/clients/", headers=auth(t),
                      json={"full_name": "Up Client", "email": "up@c.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(t),
                          json={"title": "Up v. State", "client_id": cid, "status": "open"}).json()["id"]
    r = client.post("/api/documents/upload", headers=auth(t),
                    data={"case_id": case_id},
                    files={"file": ("malware.exe", io.BytesIO(b"MZ..."), "application/octet-stream")})
    assert r.status_code == 400
    # sanity: an allowed type still uploads
    r2 = client.post("/api/documents/upload", headers=auth(t),
                     data={"case_id": case_id},
                     files={"file": ("note.txt", io.BytesIO(b"hearing notes"), "text/plain")})
    assert r2.status_code == 201
