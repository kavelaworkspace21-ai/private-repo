"""
Phase A5 — real document upload, versioning, download, tenant isolation.
"""
from tests.conftest import register_and_login, auth


def _case(client, tok):
    cid = client.post("/api/clients/", headers=auth(tok),
                      json={"full_name": "C", "email": "c@e.com"}).json()["id"]
    return client.post("/api/cases/", headers=auth(tok),
                       json={"title": "Doc Case", "client_id": cid, "status": "open"}).json()["id"]


def _upload(client, tok, case_id, content=b"%PDF-1.4 hello", name="brief.pdf", ctype="application/pdf"):
    return client.post("/api/documents/upload", headers=auth(tok),
                       data={"case_id": str(case_id), "notes": "first"},
                       files={"file": (name, content, ctype)})


def test_upload_and_download(client):
    t = register_and_login(client, "doc1@firm.com")
    case_id = _case(client, t)
    r = _upload(client, t, case_id, content=b"%PDF-1.4 ORIGINAL")
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]

    dl = client.get(f"/api/documents/{doc_id}/download", headers=auth(t))
    assert dl.status_code == 200
    assert dl.content == b"%PDF-1.4 ORIGINAL"

    versions = client.get(f"/api/documents/{doc_id}/versions", headers=auth(t)).json()
    assert len(versions) == 1 and versions[0]["version_no"] == 1
    assert versions[0]["sha256"]


def test_versioning(client):
    t = register_and_login(client, "doc2@firm.com")
    case_id = _case(client, t)
    doc_id = _upload(client, t, case_id, content=b"%PDF-1.4 V1").json()["id"]

    r2 = client.post(f"/api/documents/{doc_id}/versions", headers=auth(t),
                     files={"file": ("brief_v2.pdf", b"%PDF-1.4 V2", "application/pdf")})
    assert r2.status_code == 201
    assert r2.json()["version_no"] == 2

    # latest download = v2; explicit v1 still retrievable
    assert client.get(f"/api/documents/{doc_id}/download", headers=auth(t)).content == b"%PDF-1.4 V2"
    assert client.get(f"/api/documents/{doc_id}/download?version=1", headers=auth(t)).content == b"%PDF-1.4 V1"
    assert len(client.get(f"/api/documents/{doc_id}/versions", headers=auth(t)).json()) == 2


def test_bad_file_type_rejected(client):
    t = register_and_login(client, "doc3@firm.com")
    case_id = _case(client, t)
    r = client.post("/api/documents/upload", headers=auth(t),
                    data={"case_id": str(case_id)},
                    files={"file": ("malware.exe", b"MZ...", "application/octet-stream")})
    assert r.status_code == 400


def test_upload_requires_auth(client):
    r = client.post("/api/documents/upload", data={"case_id": "1"},
                    files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 401


def test_cross_tenant_document_denied(client):
    owner = register_and_login(client, "owner@firm.com")
    case_id = _case(client, owner)
    doc_id = _upload(client, owner, case_id).json()["id"]

    intruder = register_and_login(client, "intruder@firm.com")
    assert client.get(f"/api/documents/{doc_id}/download", headers=auth(intruder)).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/versions", headers=auth(intruder)).status_code == 404
    assert client.get("/api/documents/", headers=auth(intruder)).json() == []
