"""
Advocate Workbench — WB-00 scaffolding + WB-01 engine gates (pack §6).

The hidden _gate_probe_* workflows generate deterministically (no LLM, no network),
so every gate is provable in CI: question-first, assumptions, citation hard-gate,
refusal, versioning, entitlements, tenant isolation, audit.
"""
import pytest

from tests.conftest import register_and_login, auth
from app.models.billing import KIND_RESEARCH


def _mk_session(client, tok, wtype="_gate_probe_research"):
    r = client.post("/api/workbench/sessions", headers=auth(tok),
                    json={"workflow_type": wtype})
    assert r.status_code == 201, r.text
    return r.json()


def _answer(client, tok, sid, answers, assume=False):
    return client.post(f"/api/workbench/sessions/{sid}/answers", headers=auth(tok),
                       json={"answers": answers, "proceed_with_assumptions": assume})


# ── WB-00: scaffolding ────────────────────────────────────────────────────────
def test_workbench_page_and_catalogue(client):
    assert client.get("/workbench").status_code == 200            # hub page serves
    assert client.get("/api/workbench/workflows").status_code == 401   # API needs auth
    t = register_and_login(client, "wb0@firm.com")
    flows = client.get("/api/workbench/workflows", headers=auth(t)).json()
    labels = {f["label"] for f in flows}
    assert labels == {"Case File Analysis", "Guided Drafting", "Deep Research",
                      "Judgment Analyzer", "Argument Studio", "Chat with Case File"}
    assert not any(f["type"].startswith("_gate_probe") for f in flows)   # probes hidden


def test_upload_dependent_tools_are_honest_about_wb02(client):
    t = register_and_login(client, "wb0b@firm.com")
    r = client.post("/api/workbench/sessions", headers=auth(t),
                    json={"workflow_type": "case_file_analysis"})
    assert r.status_code == 409 and "upload" in r.json()["detail"].lower()


def test_unknown_workflow_404(client):
    t = register_and_login(client, "wb0c@firm.com")
    assert client.post("/api/workbench/sessions", headers=auth(t),
                       json={"workflow_type": "nope"}).status_code == 404


# ── WB-01: question-first, always ─────────────────────────────────────────────
def test_cannot_generate_from_intake(client):
    t = register_and_login(client, "wb1@firm.com")
    s = _mk_session(client, t)
    assert s["state"] == "INTAKE"
    r = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t))
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "intake_incomplete"
    assert "topic" in r.json()["detail"]["missing"]


def test_partial_answers_stay_in_intake_with_missing_list(client):
    t = register_and_login(client, "wb1b@firm.com")
    s = _mk_session(client, t)
    r = _answer(client, t, s["id"], {})                    # nothing answered
    assert r.json()["state"] == "INTAKE" and r.json()["missing"] == ["topic"]


def test_full_answers_reach_confirm_then_generate(client):
    t = register_and_login(client, "wb1c@firm.com")
    s = _mk_session(client, t)
    r = _answer(client, t, s["id"], {"topic": "punishment for theft"})
    assert r.json()["state"] == "CONFIRM"
    g = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t))
    assert g.status_code == 200, g.text
    a = g.json()
    assert a["version"] == 1
    assert [x["name"] for x in a["sections"]] == ["Overview", "Legal Position", "Note"]
    # grounded run: the Legal Position cites a section present in the retrieved corpus
    legal = next(x for x in a["sections"] if x["name"] == "Legal Position")
    assert legal["blocked"] is False and a["citations"], "expected a verified citation"
    assert a["review_status"] == "DRAFT_FOR_ADVOCATE_REVIEW"


def test_assumption_path_records_and_prints_assumptions(client):
    t = register_and_login(client, "wb1d@firm.com")
    s = _mk_session(client, t)
    r = _answer(client, t, s["id"], {}, assume=True)       # explicit override
    body = r.json()
    assert body["state"] == "CONFIRM" and len(body["assumptions"]) == 1
    g = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t)).json()
    first = g["sections"][0]
    assert first["name"] == "Stated Assumptions" and "No answer was given" in first["content"]


# ── WB-01: citation hard-gate + refusal ───────────────────────────────────────
def test_uncited_legal_section_is_blocked_and_artifact_refused(client):
    t = register_and_login(client, "wb1e@firm.com")
    s = _mk_session(client, t)
    _answer(client, t, s["id"], {"topic": "punishment for theft", "detail": "uncited"})
    g = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t))
    assert g.status_code == 200
    a = g.json()
    legal = next(x for x in a["sections"] if x["name"] == "Legal Position")
    assert legal["blocked"] is True
    assert "withheld" in legal["content"]                  # replaced, never shown silently
    sess = client.get(f"/api/workbench/sessions/{s['id']}", headers=auth(t)).json()
    assert sess["state"] == "REFUSED"                      # sole law section blocked → refusal


def test_empty_grounding_refuses_never_guesses(client, monkeypatch):
    """The engine's WB-01 contract: retrieval returned NOTHING → every law section is
    withheld and the artifact refuses. (Semantic top-K always returns neighbours, so
    'corpus lacks the topic' relevance-thresholding is WB-04 work per the pack —
    here we pin what the engine must do once retrieval says empty.)"""
    from app.services.workbench import engine
    monkeypatch.setattr(engine, "_grounding_for", lambda s: "")
    t = register_and_login(client, "wb1f@firm.com")
    s = _mk_session(client, t)
    _answer(client, t, s["id"], {"topic": "some novel topic"})
    g = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t))
    assert g.status_code == 200
    sess = client.get(f"/api/workbench/sessions/{s['id']}", headers=auth(t)).json()
    assert sess["state"] == "REFUSED"                      # no source → no answer
    legal = next(x for x in g.json()["sections"] if x["name"] == "Legal Position")
    assert legal["blocked"] is True and "withheld" in legal["content"]


# ── WB-01: versioning + usage + audit ─────────────────────────────────────────
def test_regenerate_increments_version_and_usage(client):
    t = register_and_login(client, "wb1g@firm.com")
    s = _mk_session(client, t)
    _answer(client, t, s["id"], {"topic": "punishment for theft"})
    v1 = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t)).json()
    v2 = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t)).json()
    assert (v1["version"], v2["version"]) == (1, 2)
    used = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    assert used == 2                                       # every generation is metered


def test_quota_blocks_generation_with_402_upgrade_payload(client):
    t = register_and_login(client, "wb1h@firm.com")
    # put the tenant on Free (5 research/month)
    from app.main import app
    from app.db.session import get_db
    from app.models.user import User
    from app.services import billing as bl
    db = next(app.dependency_overrides[get_db]())
    try:
        tid = db.query(User).filter(User.email == "wb1h@firm.com").first().tenant_id
        sub = bl.get_subscription(db, tid)
        sub.plan_code, sub.status, sub.trial_end = "free", "active", None
        db.commit()
    finally:
        db.close()
    s = _mk_session(client, t)
    _answer(client, t, s["id"], {"topic": "punishment for theft"})
    for _ in range(5):
        assert client.post(f"/api/workbench/sessions/{s['id']}/generate",
                           headers=auth(t)).status_code == 200
    r6 = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t))
    assert r6.status_code == 402
    assert r6.json()["detail"]["upgrade_url"] == "/pricing"


def test_workbench_mutations_are_audited(client):
    client.post("/api/auth/register", json={"full_name": "WB Admin", "email": "wbadmin@firm.com",
                                            "password": "Sup3rSecret!", "role": "firm_admin"})
    t = client.post("/api/auth/login", json={"email": "wbadmin@firm.com",
                                             "password": "Sup3rSecret!"}).json()["access_token"]
    s = _mk_session(client, t)
    _answer(client, t, s["id"], {"topic": "punishment for theft"})
    client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t))
    actions = [a["action"] for a in client.get("/api/audit", headers=auth(t)).json()]
    for expected in ("workbench_session_created", "workbench_intake_updated",
                     "workbench_artifact_generated"):
        assert expected in actions, f"missing audit action {expected}"


# ── WB-01: tenant isolation ───────────────────────────────────────────────────
def test_cross_tenant_session_and_artifact_are_404(client):
    t1 = register_and_login(client, "wbiso1@firm.com")
    t2 = register_and_login(client, "wbiso2@firm.com")
    s = _mk_session(client, t1)
    _answer(client, t1, s["id"], {"topic": "punishment for theft"})
    a = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t1)).json()
    assert client.get(f"/api/workbench/sessions/{s['id']}", headers=auth(t2)).status_code == 404
    assert client.get(f"/api/workbench/artifacts/{a['id']}", headers=auth(t2)).status_code == 404
    assert client.get("/api/workbench/artifacts", headers=auth(t2)).json() == []
    assert client.post(f"/api/workbench/artifacts/{a['id']}/save-to-review",
                       headers=auth(t2), json={}).status_code == 404


# ── WB-01: review-queue handoff ───────────────────────────────────────────────
def test_artifact_flows_into_the_governed_review_queue(client):
    t = register_and_login(client, "wbrev@firm.com")
    s = _mk_session(client, t)
    _answer(client, t, s["id"], {"topic": "punishment for theft"})
    a = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t)).json()
    r = client.post(f"/api/workbench/artifacts/{a['id']}/save-to-review",
                    headers=auth(t), json={})
    assert r.status_code == 201
    d = r.json()
    assert d["status"] == "DRAFT_FOR_ADVOCATE_REVIEW"
    drafts = client.get("/api/drafts/", headers=auth(t)).json()
    assert any(x["id"] == d["draft_id"] for x in drafts)
    full = client.get(f"/api/drafts/{d['draft_id']}", headers=auth(t)).json()
    assert "## Legal Position" in full["content"]          # sections render to markdown
