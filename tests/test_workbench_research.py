"""
WB-04 — Deep Research + Legal Memo (pack §5 W3 + §6 WB-04).

Kanoon and the LLM are stubbed: what's under test is the authorities discipline —
[An] markers resolve only to live-retrieved judgments with REAL links, Conflicting
Views needs both sides, the good-law caveat is guaranteed, the memo variant swaps
the schema, and the artifact library doubles as research history.
"""
import pytest

from tests.conftest import register_and_login, auth
from app.services.workbench import engine
from app.services.workbench.workflows import WORKFLOWS

PACK_SCHEMA = WORKFLOWS["deep_research"]["sections"]
MEMO_SCHEMA = WORKFLOWS["deep_research"]["variants"]["memo"]["sections"]

GROUNDING = ("VERIFIED STATUTORY TEXT\nSection 138 of the Negotiable Instruments Act, 1881 — "
             "Dishonour of cheque for insufficiency, etc., of funds in the account. [verbatim]")

AUTHS = [
    {"ref": "A1", "title": "Dashrath Rupsingh Rathod v. State of Maharashtra",
     "court": "Supreme Court of India", "date": "2014-08-01",
     "url": "https://indiankanoon.org/doc/110270205/", "good_law": "unverified"},
    {"ref": "A2", "title": "Bridgestone India v. Inderpal Singh",
     "court": "Supreme Court of India", "date": "2015-12-01",
     "url": "https://indiankanoon.org/doc/34556456/", "good_law": "unverified"},
    {"ref": "A3", "title": "Some High Court ruling on s.138 territoriality",
     "court": "Bombay High Court", "date": "2016-03-04",
     "url": "https://indiankanoon.org/doc/99887766/", "good_law": "unverified"},
]


def _stub(mode="good"):
    def gen(wf, s, grounding, file_ctx="", schema=None, auths=None):
        schema = schema or engine.resolve_schema(wf, s)
        out = []
        for name in schema["sections"]:
            if name == "Leading Supreme Court Authorities":
                body = ("On territorial jurisdiction see [A1]; the position after the 2015 "
                        "amendment appears in [A2]." if mode != "fabricated_ref"
                        else "The leading case is [A9] which settles everything.")
            elif name == "Relevant High Court Authorities":
                body = "The High Court view appears in [A3]."
            elif name == "Conflicting Views":
                body = ("Pre-amendment, [A1] restricted jurisdiction; [A3] read the amendment "
                        "as restoring the payee's forum." if mode != "one_sided"
                        else "Some doubt existed; see [A1].")
            elif name in ("Current Legal Position", "Conclusion & Current Position"):
                body = ("Section 138 of the Negotiable Instruments Act governs; jurisdiction "
                        "now lies with the payee-bank's court.")
            elif name in schema["law_sections"]:
                body = "Section 138 of the Negotiable Instruments Act applies squarely."
            elif name in schema["authority_sections"]:
                body = "See [A1] and [A2]."
            else:
                body = "Structured research note tied to the stated issue."
            out.append(f"## {name}\n{body}")
        out.append("Draft for advocate review. Verify facts, jurisdiction, limitation, "
                   "court rules, and latest case law before filing.")
        return "\n\n".join(out)
    return gen


@pytest.fixture()
def research_env(monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_authorities_for", lambda s, limit=8: list(AUTHS))
    monkeypatch.setattr(engine, "_llm_generate", _stub("good"))
    return monkeypatch


def _session(client, tok, extra=None):
    s = client.post("/api/workbench/sessions", headers=auth(tok),
                    json={"workflow_type": "deep_research"}).json()
    answers = {"jurisdiction": "Telangana", "statute": "NI Act s.138",
               "stage": "pre-filing", "relief": "prosecution",
               "issues": "territorial jurisdiction for a s.138 complaint"}
    answers.update(extra or {})
    client.post(f"/api/workbench/sessions/{s['id']}/answers", headers=auth(tok),
                json={"answers": answers})
    return s


def _generate(client, tok, s):
    r = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(tok))
    assert r.status_code == 200, r.text
    return r.json()


# ── Research pack ─────────────────────────────────────────────────────────────
def test_research_pack_authorities_resolve_to_real_links(client, research_env):
    t = register_and_login(client, "dr1@firm.com")
    a = _generate(client, t, _session(client, t))
    assert [x["name"] for x in a["sections"]] == PACK_SCHEMA
    sc = next(x for x in a["sections"] if x["name"] == "Leading Supreme Court Authorities")
    assert [c["ref"] for c in sc["authorities"]] == ["A1", "A2"]
    assert all(c["url"].startswith("https://indiankanoon.org/doc/") for c in sc["authorities"])
    hc = next(x for x in a["sections"] if x["name"] == "Relevant High Court Authorities")
    assert [c["ref"] for c in hc["authorities"]] == ["A3"]


def test_fabricated_authority_marker_is_stripped(client, monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_authorities_for", lambda s, limit=8: list(AUTHS))
    monkeypatch.setattr(engine, "_llm_generate", _stub("fabricated_ref"))
    t = register_and_login(client, "dr2@firm.com")
    a = _generate(client, t, _session(client, t))
    sc = next(x for x in a["sections"] if x["name"] == "Leading Supreme Court Authorities")
    assert "[A9]" not in sc["content"]
    assert "removed: unverified authority" in sc["content"]
    assert sc["authorities"] == [] or all(c["ref"] != "A9" for c in sc["authorities"])


def test_conflicting_views_requires_sources_on_both_sides(client, monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_authorities_for", lambda s, limit=8: list(AUTHS))
    monkeypatch.setattr(engine, "_llm_generate", _stub("one_sided"))
    t = register_and_login(client, "dr3@firm.com")
    a = _generate(client, t, _session(client, t))
    cv = next(x for x in a["sections"] if x["name"] == "Conflicting Views")
    assert cv["content"] == engine.NO_CONFLICT_NOTE
    assert cv["authorities"] == []


def test_two_sided_conflict_is_presented_with_both_authorities(client, research_env):
    t = register_and_login(client, "dr4@firm.com")
    a = _generate(client, t, _session(client, t))
    cv = next(x for x in a["sections"] if x["name"] == "Conflicting Views")
    assert {c["ref"] for c in cv["authorities"]} == {"A1", "A3"}


def test_good_law_caveat_is_guaranteed_on_current_position(client, research_env):
    t = register_and_login(client, "dr5@firm.com")
    a = _generate(client, t, _session(client, t))
    pos = next(x for x in a["sections"] if x["name"] == "Current Legal Position")
    assert "good-law" in pos["content"].lower()
    assert "confirm treatment" in pos["content"].lower()


def test_kanoon_down_degrades_honestly_not_fabricating(client, monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_authorities_for", lambda s, limit=8: [])   # service down
    monkeypatch.setattr(engine, "_llm_generate", _stub("good"))
    t = register_and_login(client, "dr6@firm.com")
    a = _generate(client, t, _session(client, t))
    sc = next(x for x in a["sections"] if x["name"] == "Leading Supreme Court Authorities")
    assert sc["content"] == engine.NO_AUTHORITIES_NOTE and sc["authorities"] == []
    sess_state = client.get(f"/api/workbench/sessions/{a['session_id']}", headers=auth(t)).json()
    assert sess_state["state"] == "COMPLETE"     # statutes still carried the artifact


# ── Legal Memo variant ────────────────────────────────────────────────────────
def test_memo_output_type_swaps_the_schema(client, research_env):
    t = register_and_login(client, "dr7@firm.com")
    s = _session(client, t, extra={"output_type": "memo"})
    got = client.get(f"/api/workbench/sessions/{s['id']}", headers=auth(t)).json()
    assert got["sections_planned"] == MEMO_SCHEMA          # intake answer resolves the variant
    a = _generate(client, t, s)
    assert [x["name"] for x in a["sections"]] == MEMO_SCHEMA
    concl = next(x for x in a["sections"] if x["name"] == "Conclusion & Current Position")
    assert "good-law" in concl["content"].lower()          # caveat follows the variant too


# ── Research history ──────────────────────────────────────────────────────────
def test_artifact_library_filters_by_type_as_research_history(client, research_env):
    t = register_and_login(client, "dr8@firm.com")
    _generate(client, t, _session(client, t))
    hist = client.get("/api/workbench/artifacts?artifact_type=deep_research",
                      headers=auth(t)).json()
    assert len(hist) == 1 and hist[0]["artifact_type"] == "deep_research"
    assert client.get("/api/workbench/artifacts?artifact_type=case_file_analysis",
                      headers=auth(t)).json() == []
