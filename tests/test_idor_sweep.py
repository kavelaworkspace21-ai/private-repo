"""Cross-tenant IDOR sweep — the top-level matter objects the existing sweep
(test_tenant_rbac_deep) did NOT cover: cases, clients, and documents (incl. download + versions).
Tenant B must never read, modify, delete, or download tenant A's objects by id. The app convention
is 404 (not 403) so existence isn't revealed. Either this passes (G7 evidence) or it finds a real
IDOR to fix.
"""
from tests.conftest import register_and_login, auth


def _client_id(client, tok, email="idc@x.com"):
    r = client.post("/api/clients/", headers=auth(tok),
                    json={"full_name": "Client X", "email": email})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _case_id(client, tok, client_id):
    r = client.post("/api/cases/", headers=auth(tok),
                    json={"title": "Confidential Matter", "client_id": client_id, "status": "open"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_cross_tenant_idor_cases_and_clients(client):
    t1 = register_and_login(client, "idor-a@firm.com")
    t2 = register_and_login(client, "idor-b@firm.com")
    cid = _client_id(client, t1, "a-client@x.com")
    case_id = _case_id(client, t1, cid)

    # owner can read its own (so a t2 404 means isolation, not just absence)
    assert client.get(f"/api/cases/{case_id}", headers=auth(t1)).status_code == 200
    assert client.get(f"/api/clients/{cid}", headers=auth(t1)).status_code == 200

    # tenant B: every verb on both objects denied
    for path, patch_body in ((f"/api/cases/{case_id}", {"title": "hijacked"}),
                             (f"/api/clients/{cid}", {"full_name": "hijacked"})):
        assert client.get(path, headers=auth(t2)).status_code == 404, f"GET leaked {path}"
        assert client.patch(path, headers=auth(t2), json=patch_body).status_code == 404, \
            f"PATCH mutated {path}"
        assert client.delete(path, headers=auth(t2)).status_code == 404, f"DELETE removed {path}"

    # list endpoints are tenant-scoped
    assert client.get("/api/cases/", headers=auth(t2)).json() == []
    assert client.get("/api/clients/", headers=auth(t2)).json() == []

    # and t1's objects still exist + unchanged after t2's attempts
    assert client.get(f"/api/cases/{case_id}", headers=auth(t1)).json()["title"] == "Confidential Matter"


def test_cross_tenant_idor_documents_including_download(client):
    t1 = register_and_login(client, "idor-doc-a@firm.com")
    t2 = register_and_login(client, "idor-doc-b@firm.com")
    cid = _client_id(client, t1, "doc-client@x.com")
    case_id = _case_id(client, t1, cid)

    up = client.post("/api/documents/upload", headers=auth(t1),
                     data={"case_id": str(case_id)},
                     files={"file": ("privileged.pdf", b"%PDF-1.4 attorney-client privileged",
                                     "application/pdf")})
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]

    # owner can read + download
    assert client.get(f"/api/documents/{doc_id}", headers=auth(t1)).status_code == 200
    assert client.get(f"/api/documents/{doc_id}/download", headers=auth(t1)).status_code == 200

    # tenant B: no metadata, no download of privileged content, no versions, no delete
    assert client.get(f"/api/documents/{doc_id}", headers=auth(t2)).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/download", headers=auth(t2)).status_code == 404, \
        "cross-tenant document DOWNLOAD leaked privileged content"
    assert client.get(f"/api/documents/{doc_id}/versions", headers=auth(t2)).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=auth(t2)).status_code == 404

    # still there for the owner
    assert client.get(f"/api/documents/{doc_id}", headers=auth(t1)).status_code == 200
