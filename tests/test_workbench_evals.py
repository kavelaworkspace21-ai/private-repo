"""
LSAI-WB-09 — the Workbench eval suite (pack §6). Cases are data
(`ai/evals/workbench/eval_cases.py`); this runner executes every case through the REAL
engine + API with deterministic stubs (CI never touches a model provider).
Threshold: 100% — every case is a doctrine gate.
"""
import io
import itertools

import pytest

from tests.conftest import register_and_login, auth
from app.services.workbench import engine
from app.services.workbench.workflows import WORKFLOWS
from ai.evals.workbench.eval_cases import EVAL_CASES, counts

FILE_TEXT = ("Complaint under section 138. The complainant Ramesh Kumar supplied cement "
             "under invoice INV-77. Cheque number 445566 was drawn on Canara Bank and "
             "returned unpaid on 12.06.2026. The statutory notice was despatched on "
             "15 July 2026 by registered post.")
RATIO = "The offence is complete when the cheque is returned unpaid and the notice remains unheeded"
JUDGMENT_TEXT = f"State v. Test.\n1. {RATIO} within the statutory period."
GROUNDING = ("VERIFIED STATUTORY TEXT\nSection 138 of the Negotiable Instruments Act, 1881 — "
             "Dishonour of cheque. [verbatim]")
AUTHS = [{"ref": "A1", "title": "Case One", "court": "SC", "date": "2014",
          "url": "https://indiankanoon.org/doc/111/", "good_law": "unverified"},
         {"ref": "A2", "title": "Case Two", "court": "SC", "date": "2015",
          "url": "https://indiankanoon.org/doc/222/", "good_law": "unverified"}]

_seq = itertools.count(1)


def _needs_upload(wtype):
    return WORKFLOWS[wtype].get("needs_upload")


def _min_answers(wtype):
    return {q["key"]: f"stated {q['key']}" for q in WORKFLOWS[wtype]["intake"] if q["required"]}


def _make_stub(case):
    cat, target = case["category"], case.get("section")

    def gen(wf, s, grounding, file_ctx="", schema=None, auths=None, **_kw):
        schema = schema or engine.resolve_schema(wf, s)
        out = []
        for name in schema["sections"]:
            if cat == "banned_phrase" and name == schema["sections"][0]:
                body = f"Preparation note [p.1]. {case['phrase']} — verify everything."
            elif cat == "uncited_law" and name == target:
                body = "The position is clearly settled in our favour."     # uncited on purpose
            elif cat == "file_page_refs" and name == target:
                body = "A factual claim with no page anchor at all."
            elif cat == "fabricated_authority" and name == target:
                body = "The leading case is [A9] which settles everything."
            elif cat == "one_sided_conflict" and name == "Conflicting Views":
                body = "Some doubt existed; see [A1]."
            elif name == "Conflicting Views":
                body = "Pre-amendment [A1]; post-amendment [A2] took the other view."
            elif cat == "verbatim_paraphrase" and name == "Key Quotable Passages":
                body = '"The offence happens once the cheque bounces and notice is ignored" [p.1]'
            elif cat == "verbatim_wrong_page" and name == "Key Quotable Passages":
                body = f'"{RATIO}" [p.9]'
            elif name == "Key Quotable Passages":
                body = f'The court held: "{RATIO}" [p.1]'
            elif name in schema.get("authority_sections", []):
                body = "See [A1] and [A2]."
            elif name in schema.get("law_sections", []):
                body = "Section 138 of the Negotiable Instruments Act governs [p.1]."
            elif name in schema.get("file_sections", []):
                body = "Anchored in the record [p.1]."
            else:
                body = "Qualitative preparation note."
            out.append(f"## {name}\n{body}")
        out.append("Draft for advocate review. Verify facts, jurisdiction, limitation, "
                   "court rules, and latest case law before filing.")
        return "\n\n".join(out)
    return gen


def _session_for(client, tok, wtype):
    upload_ids = []
    if _needs_upload(wtype):
        text = JUDGMENT_TEXT if wtype == "judgment_analyzer" else FILE_TEXT
        u = client.post("/api/workbench/uploads", headers=auth(tok),
                        files={"file": ("f.txt", io.BytesIO(text.encode()), "text/plain")})
        upload_ids = [u.json()["id"]]
    r = client.post("/api/workbench/sessions", headers=auth(tok),
                    json={"workflow_type": wtype, "upload_ids": upload_ids})
    assert r.status_code == 201, r.text
    return r.json()


def _run_engine_case(client, monkeypatch, case):
    wtype, cat = case["workflow"], case["category"]
    monkeypatch.setattr(engine, "_grounding_for",
                        (lambda s: "") if cat == "no_source" else (lambda s: GROUNDING))
    monkeypatch.setattr(engine, "_authorities_for", lambda s, limit=8: list(AUTHS))
    monkeypatch.setattr(engine, "_llm_generate", _make_stub(case))
    tok = register_and_login(client, f"ev{next(_seq)}@firm.com")
    s = _session_for(client, tok, wtype)

    if cat == "question_first":
        r = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(tok))
        assert r.status_code == 409 and r.json()["detail"]["error"] == "intake_incomplete"
        return

    answers = _min_answers(wtype)
    if cat == "prediction_probe":
        answers[list(answers)[-1]] = case["probe"]
    if cat == "assumptions":
        first = list(answers)[0]
        client.post(f"/api/workbench/sessions/{s['id']}/answers", headers=auth(tok),
                    json={"answers": {first: answers[first]}, "proceed_with_assumptions": True})
    else:
        client.post(f"/api/workbench/sessions/{s['id']}/answers", headers=auth(tok),
                    json={"answers": answers})

    g = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(tok))

    if cat == "prediction_probe":
        assert g.status_code == 422 and g.json()["detail"]["error"] == "prediction_refused"
        return
    assert g.status_code == 200, g.text
    a = g.json()
    secs = {x["name"]: x for x in a["sections"]}

    if cat == "banned_phrase":
        joined = " ".join(x["content"] for x in a["sections"]).lower()
        assert case["phrase"] not in joined
        assert "[removed: non-compliant claim]" in joined
    elif cat == "uncited_law":
        assert secs[case["section"]]["blocked"] and "withheld" in secs[case["section"]]["content"]
    elif cat == "no_source":
        st = client.get(f"/api/workbench/sessions/{s['id']}", headers=auth(tok)).json()
        assert st["state"] == "REFUSED"
    elif cat == "citation_presence":
        assert a["citations"] == ["138"] and a["review_status"] == "DRAFT_FOR_ADVOCATE_REVIEW"
    elif cat == "assumptions":
        assert a["sections"][0]["name"] == "Stated Assumptions"
    elif cat == "cross_tenant":
        tok2 = register_and_login(client, f"ev{next(_seq)}b@firm.com")
        assert client.get(f"/api/workbench/artifacts/{a['id']}", headers=auth(tok2)).status_code == 404
        assert client.get(f"/api/workbench/sessions/{s['id']}", headers=auth(tok2)).status_code == 404
    elif cat == "file_page_refs":
        assert secs[case["section"]]["blocked"]
    elif cat == "fabricated_authority":
        c = secs[case["section"]]["content"]
        assert "[A9]" not in c and "removed: unverified authority" in c
    elif cat == "one_sided_conflict":
        assert secs["Conflicting Views"]["content"] == engine.NO_CONFLICT_NOTE
    elif cat == "verbatim_exact_pass":
        q = secs["Key Quotable Passages"]
        assert not q["blocked"] and RATIO in q["content"]
    elif cat in ("verbatim_paraphrase", "verbatim_wrong_page"):
        assert secs["Key Quotable Passages"]["blocked"]
    else:
        raise AssertionError(f"unknown category {cat}")


def _run_file_case(client, case):
    from app.models.billing import KIND_RESEARCH
    cat = case["category"]
    tok = register_and_login(client, f"ev{next(_seq)}f@firm.com")

    if cat == "upload_reject_ext":
        r = client.post("/api/workbench/uploads", headers=auth(tok),
                        files={"file": ("m.exe", io.BytesIO(b"MZ.."), "application/octet-stream")})
        assert r.status_code == 400
        return

    u = client.post("/api/workbench/uploads", headers=auth(tok),
                    files={"file": ("c.txt", io.BytesIO(FILE_TEXT.encode()), "text/plain")}).json()

    if cat == "file_refusal":
        before = client.get("/api/billing/usage", headers=auth(tok)).json()["items"][KIND_RESEARCH]["used"]
        r = client.post(f"/api/workbench/uploads/{u['id']}/chat", headers=auth(tok),
                        json={"question": case["q"]}).json()
        assert r["refused"] is True and r["anchors"] == []
        after = client.get("/api/billing/usage", headers=auth(tok)).json()["items"][KIND_RESEARCH]["used"]
        assert after == before
    elif cat == "file_anchor":
        r = client.post(f"/api/workbench/uploads/{u['id']}/chat", headers=auth(tok),
                        json={"question": case["q"]}).json()
        assert r["refused"] is False
        assert any(a["page"] == case["expect_page"] for a in r["anchors"])
    elif cat == "upload_isolation":
        tok2 = register_and_login(client, f"ev{next(_seq)}g@firm.com")
        assert client.post(f"/api/workbench/uploads/{u['id']}/chat", headers=auth(tok2),
                           json={"question": "anything about the cheque"}).status_code == 404
    elif cat == "retention_delete":
        from datetime import timedelta
        from app.util.time import utcnow
        from pathlib import Path
        from app.main import app
        from app.db.session import get_db
        from app.models.workbench import WorkbenchUpload
        from app.services.workbench.uploads import purge_expired
        db = next(app.dependency_overrides[get_db]())
        try:
            row = db.get(WorkbenchUpload, u["id"])
            stored = Path(row.anchors_ref)
            row.delete_after = utcnow() - timedelta(hours=1)
            db.commit()
            assert purge_expired(db) == 1 and not stored.exists()
        finally:
            db.close()
    else:
        raise AssertionError(f"unknown file category {cat}")


def test_every_workflow_has_at_least_ten_eval_cases():
    c = counts()
    assert set(c) == set(k for k in WORKFLOWS if not k.startswith("_gate_probe"))
    assert all(v >= 10 for v in c.values()), c
    assert len(EVAL_CASES) >= 60


@pytest.mark.parametrize("case", EVAL_CASES,
                         ids=[f"{c['workflow']}-{c['category']}-{i}"
                              for i, c in enumerate(EVAL_CASES)])
def test_workbench_eval(case, client, monkeypatch):
    if case["workflow"] == "chat_with_file":
        _run_file_case(client, case)
    else:
        _run_engine_case(client, monkeypatch, case)
