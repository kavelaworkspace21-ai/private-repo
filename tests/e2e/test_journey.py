"""
End-to-end advocate journey (CLAUDE.md section 7).
Must stay green after every sprint. AI steps are asserted for safe behaviour without
requiring a live OpenAI key (deterministic in CI).
"""
from datetime import date, timedelta

from tests.conftest import register_and_login, auth
from app.ai.safety import DRAFT_DISCLAIMER, sanitize_answer, is_answerable, REFUSAL_MESSAGE


def test_full_advocate_journey(client):
    # 1-2. Advocate registers (creates tenant) and logs in
    adv = register_and_login(client, "journey@firm.com", "Journey Advocate")

    # 3. Create a client
    r = client.post("/api/clients/", headers=auth(adv),
                    json={"full_name": "Ramesh Kumar", "email": "ramesh@c.com"})
    assert r.status_code == 201
    client_id = r.json()["id"]

    # 4. Create a matter (case) linked to the client
    r = client.post("/api/cases/", headers=auth(adv),
                    json={"title": "Ramesh v. State", "client_id": client_id, "status": "open"})
    assert r.status_code == 201
    case_id = r.json()["id"]

    # 5. Add a hearing to the court diary
    r = client.post("/api/diary/entries", headers=auth(adv), json={
        "case_id": case_id, "hearing_date": date.today().isoformat(),
        "court_name": "Sessions Court, Tis Hazari", "stage": "arguments",
    })
    assert r.status_code == 201, r.text

    # 6. Create a task with a deadline
    r = client.post("/api/diary/tasks", headers=auth(adv), json={
        "case_id": case_id, "title": "File vakalatnama",
        "due_date": (date.today() + timedelta(days=3)).isoformat(),
    })
    assert r.status_code == 201, r.text

    # Dashboard reflects the hearing for this tenant
    today = client.get("/api/diary/today", headers=auth(adv))
    assert today.status_code == 200
    assert len(today.json()["today"]) == 1

    # 8. Generate a draft -> export to DOCX (export needs no AI key)
    sample = "IN THE COURT OF SESSIONS JUDGE\n\nApplication for bail."
    r = client.post("/api/drafting/export", headers=auth(adv),
                    json={"document_type": "regular_bail", "content": sample, "format": "docx"})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # .docx is a zip
    assert "attachment" in r.headers.get("content-disposition", "")

    # 10. A second tenant cannot see any of tenant one's data (isolation)
    other = register_and_login(client, "outsider@firm.com", "Outsider")
    assert client.get("/api/cases/", headers=auth(other)).json() == []
    assert client.get(f"/api/cases/{case_id}", headers=auth(other)).status_code == 404


def test_no_source_no_answer_contract():
    """Section 2.1 invariant the research endpoint relies on."""
    assert is_answerable("") is False
    assert "from memory" in REFUSAL_MESSAGE


def test_draft_disclaimer_and_banned_phrase_invariants():
    """Section 2.6/2.7 invariants enforced on every draft/answer."""
    assert sanitize_answer("you will win") != "you will win"
    assert DRAFT_DISCLAIMER.startswith("Draft for advocate review")


def test_workbench_journey_and_isolation(client, monkeypatch):
    """WB-09 e2e extension (pack §6): upload file → Case Analysis → Argument Studio pack
    → export → a SECOND tenant sees none of it. Deterministic stubs; real engine + gates."""
    import io
    from app.services.workbench import engine

    GROUNDING = ("VERIFIED STATUTORY TEXT\nSection 138 of the Negotiable Instruments Act, "
                 "1881 — Dishonour of cheque. [verbatim]")

    def stub(wf, s, grounding, file_ctx="", schema=None, auths=None, **_kw):
        schema = schema or engine.resolve_schema(wf, s)
        out = []
        for name in schema["sections"]:
            if name == "Suggested Litigation Strategy":
                body = "- Obtain the return memo [p.1]\n- File before the JMFC [p.1]"
            elif name in schema.get("authority_sections", []):
                body = "Section 138 of the Negotiable Instruments Act grounds this [p.1]."
            elif name in schema.get("law_sections", []):
                body = "Section 138 of the Negotiable Instruments Act governs [p.1]."
            elif name in schema.get("file_sections", []):
                body = "Anchored in the record [p.1]."
            else:
                body = "Preparation note."
            out.append(f"## {name}\n{body}")
        out.append("Draft for advocate review. Verify facts, jurisdiction, limitation, "
                   "court rules, and latest case law before filing.")
        return "\n\n".join(out)

    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_authorities_for", lambda s, limit=8: [])
    monkeypatch.setattr(engine, "_llm_generate", stub)

    adv = register_and_login(client, "wbjourney@firm.com", "WB Journey")
    cid = client.post("/api/clients/", headers=auth(adv),
                      json={"full_name": "J Client", "email": "jc@c.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(adv),
                          json={"title": "J v. State", "client_id": cid,
                                "status": "open"}).json()["id"]

    # 1. upload the case file
    up = client.post("/api/workbench/uploads", headers=auth(adv),
                     files={"file": ("case.txt", io.BytesIO(
                         b"Cheque 445566 drawn on Canara Bank returned unpaid on 12.06.2026."),
                         "text/plain")}).json()

    # 2. Case File Analysis
    s1 = client.post("/api/workbench/sessions", headers=auth(adv),
                     json={"workflow_type": "case_file_analysis",
                           "upload_ids": [up["id"]], "matter_id": case_id}).json()
    client.post(f"/api/workbench/sessions/{s1['id']}/answers", headers=auth(adv),
                json={"answers": {"parties_side": "complainant", "court_stage": "JMFC",
                                  "relief_context": "prosecution"}})
    a1 = client.post(f"/api/workbench/sessions/{s1['id']}/generate", headers=auth(adv)).json()
    assert a1["review_status"] == "DRAFT_FOR_ADVOCATE_REVIEW"

    # 3. analysis → matter document + diary tasks
    client.post(f"/api/workbench/artifacts/{a1['id']}/save-to-matter", headers=auth(adv),
                json={"case_id": case_id})
    tasks = client.post(f"/api/workbench/artifacts/{a1['id']}/create-tasks", headers=auth(adv),
                        json={"case_id": case_id}).json()
    assert tasks["created"] >= 2

    # 4. Argument Studio pack
    s2 = client.post("/api/workbench/sessions", headers=auth(adv),
                     json={"workflow_type": "argument_studio", "matter_id": case_id}).json()
    client.post(f"/api/workbench/sessions/{s2['id']}/answers", headers=auth(adv),
                json={"answers": {k: "stated" for k in
                                  ("facts", "procedural_history", "relief", "applicable_law",
                                   "evidence", "opponents_case", "stage")}})
    a2 = client.post(f"/api/workbench/sessions/{s2['id']}/generate", headers=auth(adv)).json()
    names = [x["name"] for x in a2["sections"]]
    assert "Judge Mode: The 10 Toughest Questions" in names

    # 5. export both artifacts
    for aid in (a1["id"], a2["id"]):
        ex = client.post(f"/api/workbench/artifacts/{aid}/export", headers=auth(adv),
                         json={"format": "docx"})
        assert ex.status_code == 200 and ex.content[:2] == b"PK"

    # 6. the second tenant sees NOTHING
    outsider = register_and_login(client, "wbout@firm.com", "Outsider")
    assert client.get("/api/workbench/uploads", headers=auth(outsider)).json() == []
    assert client.get("/api/workbench/artifacts", headers=auth(outsider)).json() == []
    for res in (f"/api/workbench/sessions/{s1['id']}", f"/api/workbench/artifacts/{a1['id']}"):
        assert client.get(res, headers=auth(outsider)).status_code == 404
    assert client.post(f"/api/workbench/artifacts/{a2['id']}/export", headers=auth(outsider),
                       json={"format": "docx"}).status_code == 404
    # list endpoints are tenant-scoped: an outsider probing our case_id sees an EMPTY list
    assert client.get(f"/api/documents/?case_id={case_id}", headers=auth(outsider)).json() == []
    assert client.get(f"/api/diary/tasks?case_id={case_id}", headers=auth(outsider)).json() == []
