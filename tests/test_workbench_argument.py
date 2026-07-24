"""
WB-06 — Argument Studio (pack §5 W5 + §6 WB-06).

Under test: the three entry modes (esp. selected-citation grounding), the both-sides
citation discipline (advocate + opponent + Judge Mode all cited), fabricated-marker
stripping, the no-prediction guard, reserved-key protection, and draft metering.
Kanoon + LLM are stubbed so CI is deterministic.
"""
import pytest

from tests.conftest import register_and_login, auth
from app.models.billing import KIND_DRAFT
from app.services.workbench import engine
from app.services.workbench.workflows import WORKFLOWS

SCHEMA = WORKFLOWS["argument_studio"]["sections"]

GROUNDING = ("VERIFIED STATUTORY TEXT\nSection 138 of the Negotiable Instruments Act, 1881 — "
             "Dishonour of cheque for insufficiency, etc., of funds in the account. [verbatim]")

SELECTED = {
    "111": {"tid": "111", "title": "Dashrath Rupsingh Rathod v. State of Maharashtra",
            "court": "Supreme Court of India", "date": "2014-08-01",
            "text": "...", "url": "https://indiankanoon.org/doc/111/"},
    "222": {"tid": "222", "title": "Bridgestone India v. Inderpal Singh",
            "court": "Supreme Court of India", "date": "2015-12-01",
            "text": "...", "url": "https://indiankanoon.org/doc/222/"},
}
SENTINEL_SEARCH = [{"title": "SHOULD-NOT-APPEAR search result", "court": "X", "date": "2000",
                    "url": "https://indiankanoon.org/doc/999999/", "good_law": "unverified"}]


def _stub(mode="good"):
    def gen(wf, s, grounding, file_ctx="", schema=None, auths=None, **_kw):
        schema = schema or engine.resolve_schema(wf, s)
        out = []
        for name in schema["sections"]:
            if name == "Leading Authorities":
                body = ("The controlling authority is [A1]; see also [A2]."
                        if mode != "fabricated" else "The key case is [A9].")
            elif name == "Opposing Counsel's Best Arguments":
                body = "The respondent will lean on [A2] to resist relief."
            elif name == "Judge Mode: The 10 Toughest Questions":
                body = ("Q1: Why this forum? Response: Section 138 of the Negotiable "
                        "Instruments Act fixes jurisdiction. Q2: Distinguish the leading "
                        "case? Response: [A1] is distinguishable on facts.")
            elif name == "Relevant Statutory Provisions":
                body = "Section 138 of the Negotiable Instruments Act applies squarely."
            elif name == "Relief-Oriented Submissions":
                body = "Relief flows from Section 138 of the Negotiable Instruments Act."
            else:
                body = "Preparation note tied to the stated facts."
            out.append(f"## {name}\n{body}")
        out.append("Draft for advocate review. Verify facts, jurisdiction, limitation, "
                   "court rules, and latest case law before filing.")
        return "\n\n".join(out)
    return gen


@pytest.fixture()
def arg_env(monkeypatch):
    from app.ai import case_law
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(case_law, "fetch_document", lambda tid: SELECTED.get(str(tid)))
    monkeypatch.setattr(case_law, "search_cases", lambda q, limit=8: list(SENTINEL_SEARCH))
    monkeypatch.setattr(engine, "_llm_generate", _stub("good"))
    return monkeypatch


def _run(client, tok, citation_tids=None, relief="conviction and compensation"):
    s = client.post("/api/workbench/sessions", headers=auth(tok),
                    json={"workflow_type": "argument_studio",
                          "citation_tids": citation_tids or []}).json()
    client.post(f"/api/workbench/sessions/{s['id']}/answers", headers=auth(tok), json={"answers": {
        "facts": "Cheque dishonoured; notice unheeded.", "procedural_history": "Complaint filed",
        "relief": relief, "applicable_law": "NI Act s.138", "evidence": "cheque, memo, notice",
        "opponents_case": "denies liability", "stage": "arguments"}})
    g = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(tok))
    return s, g


def _sec(a, name):
    return next(x for x in a["sections"] if x["name"] == name)


# ── Entry mode (c): selected citations are the ONLY authority set ─────────────
def test_selected_citations_are_the_authority_set(client, arg_env):
    t = register_and_login(client, "arg1@firm.com")
    _s, g = _run(client, t, citation_tids=["https://indiankanoon.org/doc/111/", "222"])
    assert g.status_code == 200, g.text
    a = g.json()
    la = _sec(a, "Leading Authorities")
    urls = {c["url"] for c in la["authorities"]}
    assert urls == {"https://indiankanoon.org/doc/111/", "https://indiankanoon.org/doc/222/"}
    # the live-search sentinel must never leak in when the advocate selected citations
    assert all("999999" not in u for u in urls)


def test_selected_citations_survive_the_answers_round_trip(client, arg_env):
    t = register_and_login(client, "arg2@firm.com")
    s = client.post("/api/workbench/sessions", headers=auth(t),
                    json={"workflow_type": "argument_studio", "citation_tids": ["111"]}).json()
    assert s["selected_citations"] == ["111"]
    # a client cannot smuggle its own citation set through the answers endpoint
    # (reserved "_"-prefixed keys are skipped server-side, never merged)
    got = client.post(f"/api/workbench/sessions/{s['id']}/answers", headers=auth(t),
                      json={"answers": {"facts": "x", "_selected_citations": "999"}}).json()
    assert got["selected_citations"] == ["111"]
    assert "_selected_citations" not in got["answers"]


# ── Both-sides citation discipline ────────────────────────────────────────────
def test_both_sides_and_judge_mode_are_cited(client, arg_env):
    t = register_and_login(client, "arg3@firm.com")
    _s, g = _run(client, t, citation_tids=["111", "222"])
    a = g.json()
    assert [x["name"] for x in a["sections"]] == SCHEMA          # all 15
    assert _sec(a, "Leading Authorities")["authorities"]
    assert _sec(a, "Opposing Counsel's Best Arguments")["authorities"]   # opponent cited too
    jm = _sec(a, "Judge Mode: The 10 Toughest Questions")
    # Judge-mode responses cited (a resolved authority OR a verified statute both count)
    assert jm["authorities"] or "138" in jm["content"]
    assert "No live authorities" not in jm["content"]           # not wiped — it is grounded


def test_fabricated_authority_marker_is_stripped(client, monkeypatch):
    from app.ai import case_law
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(case_law, "fetch_document", lambda tid: SELECTED.get(str(tid)))
    monkeypatch.setattr(engine, "_llm_generate", _stub("fabricated"))
    t = register_and_login(client, "arg4@firm.com")
    _s, g = _run(client, t, citation_tids=["111"])
    la = _sec(g.json(), "Leading Authorities")
    assert "[A9]" not in la["content"] and "removed: unverified authority" in la["content"]


# ── No prediction, ever ───────────────────────────────────────────────────────
def test_will_i_win_probe_refused_before_cost(client, arg_env):
    t = register_and_login(client, "arg5@firm.com")
    _s, g = _run(client, t, relief="honestly, what are my chances of winning?")
    assert g.status_code == 422 and g.json()["detail"]["error"] == "prediction_refused"
    used = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_DRAFT]["used"]
    assert used == 0


# ── Metering ──────────────────────────────────────────────────────────────────
def test_argument_pack_counts_as_a_draft_unit(client, arg_env):
    t = register_and_login(client, "arg6@firm.com")
    _run(client, t, citation_tids=["111"])
    used = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_DRAFT]["used"]
    assert used == 1
