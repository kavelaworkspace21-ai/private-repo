"""Upload content sniffing (refinement) — a renamed/spoofed file must not bypass the extension
allowlist. validate() now checks magic bytes match the claimed extension.
"""
import pytest

from app.services import storage
from app.services.storage import FileTypeNotAllowed, FileTooLarge
from tests.conftest import register_and_login, auth


# ── validate(): real signatures accepted ────────────────────────────────────────
@pytest.mark.parametrize("name,data", [
    ("brief.pdf",  b"%PDF-1.4 real pdf body"),
    ("scan.png",   b"\x89PNG\r\n\x1a\n....."),
    ("photo.jpg",  b"\xff\xd8\xff\xe0 jfif"),
    ("photo.jpeg", b"\xff\xd8\xff\xe1 exif"),
    ("doc.docx",   b"PK\x03\x04 zip-ooxml"),
    ("old.doc",    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 ole"),
    ("memo.rtf",   b"{\\rtf1 body}"),
    ("notes.txt",  b"just plain hearing notes"),
])
def test_real_content_accepted(name, data):
    storage.validate(name, data)   # must not raise


# ── validate(): spoofed content rejected ────────────────────────────────────────
@pytest.mark.parametrize("name,data", [
    ("malware.pdf", b"MZ\x90\x00 this is a PE executable"),  # exe renamed to .pdf
    ("fake.pdf",    b"not a pdf at all"),
    ("fake.png",    b"GIF89a wrong image type"),
    ("fake.docx",   b"plain text, not a zip"),
    ("evil.txt",    b"PK\x03\x04 a zip renamed to txt"),      # binary masquerading as text
    ("evil2.txt",   b"MZ\x90 exe as txt"),
])
def test_spoofed_content_rejected(name, data):
    with pytest.raises(FileTypeNotAllowed):
        storage.validate(name, data)


def test_extension_and_size_gates_still_apply():
    with pytest.raises(FileTypeNotAllowed):
        storage.validate("app.exe", b"MZ anything")           # extension not allowed
    with pytest.raises(FileTooLarge):
        storage.validate("big.pdf", b"%PDF" + b"x" * (21 * 1024 * 1024))


# ── API level: a spoofed .pdf upload is rejected with 400 ────────────────────────
def test_api_rejects_spoofed_pdf_upload(client):
    tok = register_and_login(client, "upload-sec@firm.com")
    cid = client.post("/api/clients/", headers=auth(tok),
                      json={"full_name": "C", "email": "c@x.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(tok),
                          json={"title": "M", "client_id": cid, "status": "open"}).json()["id"]
    r = client.post("/api/documents/upload", headers=auth(tok),
                    data={"case_id": str(case_id)},
                    files={"file": ("invoice.pdf", b"MZ\x90 executable pretending to be a pdf",
                                    "application/pdf")})
    assert r.status_code == 400, r.text
    assert "extension" in r.text.lower() or "not allowed" in r.text.lower()
