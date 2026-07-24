"""
WB-08 — artifacts become practice objects (pack §6 WB-08).

Covers: direct DOCX/PDF export with the AI-disclosure + review-disclaimer footer,
save-to-matter (versioned Document), diary tasks from strategy items (free-tier
diary rule applies), explicit approval gating, and the end-to-end flow the pack
names as Done-when.
"""
import io

import pytest

from tests.conftest import register_and_login, auth
from app.services.workbench import engine

FILE_TEXT = ("Complaint under section 138. Cheque 445566 drawn on Canara Bank returned "
             "unpaid on 12.06.2026. Notice served 15 July 2026.")
GROUNDING = ("VERIFIED STATUTORY TEXT\nSection 138 of the Negotiable Instruments Act, 1881 — "
             "Dishonour of cheque. [verbatim]")


def _stub(with_strategy=True):
    def gen(wf, s, grounding, file_ctx="", **_kw):
        out = []
        for name in wf["sections"]:
            if name == "Suggested Litigation Strategy" and with_strategy:
                body = ("- Obtain the original returned cheque and bank memo [p.1]\n"
                        "- File the complaint before the JMFC within limitation [p.1]\n"
                        "- Serve a certified copy of the statutory notice [p.1]")
            elif name == "Further Documents Required" and with_strategy:
                body = "1. Bank statement for June 2026 [p.1]\n2. Invoice INV-77 [p.1]"
            elif name in wf.get("file_sections", []):
                body = "Anchored in the record [p.1]."
            elif name in wf.get("law_sections", []):
                body = "Section 138 of the Negotiable Instruments Act governs [p.1]."
            else:
                body = "Preparation note."
            out.append(f"## {name}\n{body}")
        out.append("Draft for advocate review. Verify facts, jurisdiction, limitation, "
                   "court rules, and latest case law before filing.")
        return "\n\n".join(out)
    return gen


@pytest.fixture()
def practice_env(monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_llm_generate", _stub(True))
    return monkeypatch


def _setup_case(client, tok):
    cid = client.post("/api/clients/", headers=auth(tok),
                      json={"full_name": "P Client", "email": "pc@c.com"}).json()["id"]
    return client.post("/api/cases/", headers=auth(tok),
                       json={"title": "P v. State", "client_id": cid, "status": "open"}).json()["id"]


def _artifact(client, tok):
    u = client.post("/api/workbench/uploads", headers=auth(tok),
                    files={"file": ("case.txt", io.BytesIO(FILE_TEXT.encode()), "text/plain")}).json()
    s = client.post("/api/workbench/sessions", headers=auth(tok),
                    json={"workflow_type": "case_file_analysis", "upload_ids": [u["id"]]}).json()
    client.post(f"/api/workbench/sessions/{s['id']}/answers", headers=auth(tok),
                json={"answers": {"parties_side": "complainant", "court_stage": "JMFC",
                                  "relief_context": "prosecution"}})
    return client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(tok)).json()


# ── Export with disclosure ────────────────────────────────────────────────────
def test_export_carries_disclosure_and_disclaimer(client, practice_env):
    t = register_and_login(client, "pr1@firm.com")
    a = _artifact(client, t)
    # the text every export renders from — must carry BOTH footers
    from app.main import app
    from app.db.session import get_db
    from app.routers.workbench import _artifact_export_text
    from app.models.workbench import WorkflowArtifact
    db = next(app.dependency_overrides[get_db]())
    try:
        row = db.get(WorkflowArtifact, a["id"])
        text = _artifact_export_text(db, row)
        assert "Draft for advocate review" in text
        assert "AI" in text and ("assist" in text.lower() or "generated" in text.lower())
    finally:
        db.close()
    # binary endpoints work
    d = client.post(f"/api/workbench/artifacts/{a['id']}/export", headers=auth(t),
                    json={"format": "docx"})
    assert d.status_code == 200 and d.content[:2] == b"PK"
    p = client.post(f"/api/workbench/artifacts/{a['id']}/export", headers=auth(t),
                    json={"format": "pdf"})
    assert p.status_code == 200 and p.content[:4] == b"%PDF"


# ── Save to matter ────────────────────────────────────────────────────────────
def test_artifact_saved_to_matter_appears_as_versioned_document(client, practice_env):
    t = register_and_login(client, "pr2@firm.com")
    case_id = _setup_case(client, t)
    a = _artifact(client, t)
    r = client.post(f"/api/workbench/artifacts/{a['id']}/save-to-matter", headers=auth(t),
                    json={"case_id": case_id})
    assert r.status_code == 201
    docs = client.get(f"/api/documents/?case_id={case_id}", headers=auth(t)).json()
    assert any(d["id"] == r.json()["document_id"] for d in docs)

    t2 = register_and_login(client, "pr3@firm.com")
    a2 = _artifact(client, t2)
    assert client.post(f"/api/workbench/artifacts/{a2['id']}/save-to-matter", headers=auth(t2),
                       json={"case_id": case_id}).status_code == 404   # someone else's matter


# ── Diary tasks from strategy ─────────────────────────────────────────────────
def test_strategy_items_become_diary_tasks(client, practice_env):
    t = register_and_login(client, "pr4@firm.com")
    case_id = _setup_case(client, t)
    a = _artifact(client, t)
    r = client.post(f"/api/workbench/artifacts/{a['id']}/create-tasks", headers=auth(t),
                    json={"case_id": case_id, "days_ahead": 5})
    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 5                       # 3 strategy + 2 documents-required
    tasks = client.get(f"/api/diary/tasks?case_id={case_id}", headers=auth(t)).json()
    titles = [x["title"] for x in tasks]
    assert any("original returned cheque" in x for x in titles)
    assert any("Invoice INV-77" in x for x in titles)


def test_no_strategy_items_is_422_and_free_tier_diary_stays_readonly(client, monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_llm_generate", _stub(False))     # no actionable bullets
    t = register_and_login(client, "pr5@firm.com")
    case_id = _setup_case(client, t)
    a = _artifact(client, t)
    assert client.post(f"/api/workbench/artifacts/{a['id']}/create-tasks", headers=auth(t),
                       json={"case_id": case_id}).status_code == 422
    # free tier: diary is read-only — the same rule bites here
    from app.main import app
    from app.db.session import get_db
    from app.models.user import User
    from app.services import billing as bl
    db = next(app.dependency_overrides[get_db]())
    try:
        tid = db.query(User).filter(User.email == "pr5@firm.com").first().tenant_id
        sub = bl.get_subscription(db, tid)
        sub.plan_code, sub.status, sub.trial_end = "free", "active", None
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/workbench/artifacts/{a['id']}/create-tasks", headers=auth(t),
                    json={"case_id": case_id})
    assert r.status_code == 402


# ── Approval gating ───────────────────────────────────────────────────────────
def test_only_advocate_approves_and_it_is_audited(client, practice_env):
    client.post("/api/auth/register", json={"full_name": "FA", "email": "pr6@firm.com",
                                            "password": "Sup3rSecret!", "role": "firm_admin"})
    t = client.post("/api/auth/login", json={"email": "pr6@firm.com",
                                             "password": "Sup3rSecret!"}).json()["access_token"]
    a = _artifact(client, t)
    assert a["review_status"] == "DRAFT_FOR_ADVOCATE_REVIEW"
    r = client.post(f"/api/workbench/artifacts/{a['id']}/approve", headers=auth(t))
    assert r.status_code == 200 and r.json()["review_status"] == "ADVOCATE_APPROVED"
    acts = [x["action"] for x in client.get("/api/audit", headers=auth(t)).json()]
    assert "workbench_artifact_approved" in acts

    client.post("/api/auth/register", json={"full_name": "C", "email": "pr7@firm.com",
                                            "password": "Sup3rSecret!", "role": "clerk"})
    ct = client.post("/api/auth/login", json={"email": "pr7@firm.com",
                                              "password": "Sup3rSecret!"}).json()["access_token"]
    assert client.post(f"/api/workbench/artifacts/{a['id']}/approve",
                       headers=auth(ct)).status_code in (403, 404)


# ── Done-when: the end-to-end flow ────────────────────────────────────────────
def test_case_analysis_flows_into_matter_and_diary_end_to_end(client, practice_env):
    t = register_and_login(client, "pr8@firm.com")
    case_id = _setup_case(client, t)
    a = _artifact(client, t)
    doc = client.post(f"/api/workbench/artifacts/{a['id']}/save-to-matter", headers=auth(t),
                      json={"case_id": case_id}).json()
    tasks = client.post(f"/api/workbench/artifacts/{a['id']}/create-tasks", headers=auth(t),
                        json={"case_id": case_id}).json()
    docs = client.get(f"/api/documents/?case_id={case_id}", headers=auth(t)).json()
    diary = client.get(f"/api/diary/tasks?case_id={case_id}", headers=auth(t)).json()
    assert any(d["id"] == doc["document_id"] for d in docs)
    assert len(diary) == tasks["created"] > 0
    ex = client.post(f"/api/workbench/artifacts/{a['id']}/export", headers=auth(t),
                     json={"format": "docx"})
    assert ex.status_code == 200 and ex.content[:2] == b"PK"
