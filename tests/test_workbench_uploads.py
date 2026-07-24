"""
WB-02 — uploads, file-grounded chat, List of Dates, retention (pack §6, LSAI-WB-02).

Everything here is deterministic: extraction, relevance threshold, refusal, chronology,
purge. (The LLM answer path degrades to page-anchored excerpts when no key is set,
which is exactly how CI runs.)
"""
import io
from datetime import datetime, timedelta

from app.util.time import utcnow
from pathlib import Path

from tests.conftest import register_and_login, auth
from app.models.billing import KIND_RESEARCH

FACTS_P1 = ("This complaint concerns a dishonoured cheque. The complainant Ramesh Kumar "
            "supplied cement to the accused firm under invoice INV-77. The cheque number "
            "445566 was drawn on Canara Bank for rupees three lakh fifty thousand.")
FACTS_P2 = ("On 12.06.2026 the cheque was presented and returned unpaid with the remark "
            "insufficient funds. A statutory notice was despatched on 15 July 2026 by "
            "registered post to the accused at Begumpet Hyderabad.")
FACTS_P3 = ("No payment was received within the statutory period. On August 3, 2026 the "
            "complainant instructed counsel to institute proceedings before the magistrate.")


def _pdf_bytes(pages: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for text in pages:
        y = 800
        for line in [text[i:i + 90] for i in range(0, len(text), 90)]:
            c.drawString(40, y, line)
            y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()


def _upload(client, tok, data: bytes, name: str):
    return client.post("/api/workbench/uploads", headers=auth(tok),
                       files={"file": (name, io.BytesIO(data), "application/octet-stream")})


def _std_upload(client, tok):
    r = _upload(client, tok, _pdf_bytes([FACTS_P1, FACTS_P2, FACTS_P3]), "case_file.pdf")
    assert r.status_code == 201, r.text
    return r.json()


# ── Upload + extraction ───────────────────────────────────────────────────────
def test_pdf_upload_extracts_pages_with_seven_day_retention(client):
    t = register_and_login(client, "up1@firm.com")
    u = _std_upload(client, t)
    assert u["page_count"] == 3
    assert u["retention_policy"] == "scratch_7d"
    days = (datetime.fromisoformat(u["delete_after"]) - utcnow()).days
    assert 6 <= days <= 7


def test_txt_upload_and_bad_types_rejected(client):
    t = register_and_login(client, "up2@firm.com")
    assert _upload(client, t, b"plain notes about the hearing", "notes.txt").status_code == 201
    assert _upload(client, t, b"MZ...", "malware.exe").status_code == 400
    assert _upload(client, t, b"", "empty.pdf").status_code == 400
    # a PDF with no extractable text (blank page) is honestly refused
    assert _upload(client, t, _pdf_bytes([""]), "scanned.pdf").status_code == 422


# ── File-grounded chat ────────────────────────────────────────────────────────
def test_chat_answers_from_file_with_page_anchors(client):
    t = register_and_login(client, "up3@firm.com")
    u = _std_upload(client, t)
    r = client.post(f"/api/workbench/uploads/{u['id']}/chat", headers=auth(t),
                    json={"question": "When was the statutory notice despatched by registered post?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refused"] is False
    assert body["anchors"], "expected page anchors"
    assert any(a["page"] == 2 for a in body["anchors"])          # the notice fact lives on p.2
    assert "p.2" in body["answer"] or "15 July 2026" in body["answer"]


def test_chat_refuses_questions_outside_the_file_at_no_cost(client):
    t = register_and_login(client, "up4@firm.com")
    u = _std_upload(client, t)
    before = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    r = client.post(f"/api/workbench/uploads/{u['id']}/chat", headers=auth(t),
                    json={"question": "Explain quantum entanglement thermodynamics parameters"})
    body = r.json()
    assert body["refused"] is True and body["anchors"] == []
    assert "does not appear to contain" in body["answer"]
    after = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    assert after == before                                       # refusal is free


def test_chat_is_metered_when_it_answers(client):
    t = register_and_login(client, "up5@firm.com")
    u = _std_upload(client, t)
    before = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    client.post(f"/api/workbench/uploads/{u['id']}/chat", headers=auth(t),
                json={"question": "Which bank was the cheque number 445566 drawn on?"})
    after = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    assert after == before + 1


# ── List of Dates ─────────────────────────────────────────────────────────────
def test_list_of_dates_builds_sorted_court_chronology(client):
    t = register_and_login(client, "up6@firm.com")
    u = _std_upload(client, t)
    r = client.post(f"/api/workbench/uploads/{u['id']}/list-of-dates", headers=auth(t))
    assert r.status_code == 200
    body = r.json()
    dates = [row["date"] for row in body["rows"]]
    assert dates == sorted(dates)                                # chronological
    assert "2026-06-12" in dates and "2026-07-15" in dates and "2026-08-03" in dates
    pages = {row["date"]: row["page"] for row in body["rows"]}
    assert pages["2026-06-12"] == 2 and pages["2026-08-03"] == 3
    assert "| Date | Event | Page |" in body["markdown"]
    assert "Draft for advocate review" in body["markdown"]


def test_list_of_dates_costs_no_plan_units(client):
    t = register_and_login(client, "up7@firm.com")
    u = _std_upload(client, t)
    before = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    client.post(f"/api/workbench/uploads/{u['id']}/list-of-dates", headers=auth(t))
    after = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    assert after == before                                       # extraction, not generation


# ── Retention ─────────────────────────────────────────────────────────────────
def test_purge_deletes_expired_scratch_uploads_and_files(client):
    t = register_and_login(client, "up8@firm.com")
    u = _std_upload(client, t)
    from app.main import app
    from app.db.session import get_db
    from app.models.workbench import WorkbenchUpload
    from app.services.workbench.uploads import purge_expired
    db = next(app.dependency_overrides[get_db]())
    try:
        row = db.get(WorkbenchUpload, u["id"])
        stored, sidecar = Path(row.anchors_ref), Path(row.extracted_text_ref)
        assert stored.exists() and sidecar.exists()
        row.delete_after = utcnow() - timedelta(hours=1)
        db.commit()
        assert purge_expired(db) == 1
        assert db.get(WorkbenchUpload, u["id"]) is None
        assert not stored.exists() and not sidecar.exists()      # bytes actually gone
        assert purge_expired(db) == 0                            # idempotent
    finally:
        db.close()


# ── Tenant isolation ──────────────────────────────────────────────────────────
def test_uploads_are_tenant_isolated(client):
    t1 = register_and_login(client, "up9@firm.com")
    t2 = register_and_login(client, "up10@firm.com")
    u = _std_upload(client, t1)
    assert client.post(f"/api/workbench/uploads/{u['id']}/chat", headers=auth(t2),
                       json={"question": "what does the file say about the cheque"}).status_code == 404
    assert client.post(f"/api/workbench/uploads/{u['id']}/list-of-dates",
                       headers=auth(t2)).status_code == 404
    assert client.get("/api/workbench/uploads", headers=auth(t2)).json() == []


# ── Save to matter ────────────────────────────────────────────────────────────
def test_save_to_matter_promotes_upload_to_versioned_document(client):
    t = register_and_login(client, "up11@firm.com")
    cid = client.post("/api/clients/", headers=auth(t),
                      json={"full_name": "Up Client", "email": "upc@c.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(t),
                          json={"title": "Up v. State", "client_id": cid,
                                "status": "open"}).json()["id"]
    u = _std_upload(client, t)
    r = client.post(f"/api/workbench/uploads/{u['id']}/save-to-matter", headers=auth(t),
                    json={"case_id": case_id})
    assert r.status_code == 201
    doc_id = r.json()["document_id"]
    docs = client.get(f"/api/documents/?case_id={case_id}", headers=auth(t)).json()
    assert any(d["id"] == doc_id for d in docs)
    listed = client.get("/api/workbench/uploads", headers=auth(t)).json()
    mine = next(x for x in listed if x["id"] == u["id"])
    assert mine["retention_policy"] == "saved_to_matter" and mine["delete_after"] is None

    # someone else's case id → 404, never a link
    outsider_case = case_id
    t2 = register_and_login(client, "up12@firm.com")
    u2 = _std_upload(client, t2)
    assert client.post(f"/api/workbench/uploads/{u2['id']}/save-to-matter", headers=auth(t2),
                       json={"case_id": outsider_case}).status_code == 404
