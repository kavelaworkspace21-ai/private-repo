"""
WB-05 — Judgment Analyzer (pack §5 W4 + §6 WB-05).

The signature gate: Key Quotable Passages must be EXACT substrings of the judgment
text with pinpoint page refs — paraphrase presented as quotation is a test failure.
LLM + Kanoon are stubbed; the gates are what's under test.
"""
import io

import pytest

from tests.conftest import register_and_login, auth
from app.services.workbench import engine
from app.services.workbench.workflows import WORKFLOWS

SCHEMA = WORKFLOWS["judgment_analyzer"]["sections"]

# The "judgment": page 1 carries the ratio sentence we will quote.
RATIO_SENTENCE = ("The offence under Section 138 is committed no sooner the cheque "
                  "is returned unpaid and the notice remains unheeded")
JUDGMENT_TEXT = (
    "Dashrath Rupsingh Rathod v. State of Maharashtra\nSupreme Court of India\n\n"
    f"1. {RATIO_SENTENCE} within the statutory period. "
    "2. We hold that territorial jurisdiction is restricted to the court within whose "
    "local jurisdiction the offence was committed."
)


def _upload_judgment(client, tok):
    r = client.post("/api/workbench/uploads", headers=auth(tok),
                    files={"file": ("judgment.txt", io.BytesIO(JUDGMENT_TEXT.encode()),
                                    "text/plain")})
    assert r.status_code == 201, r.text
    return r.json()


def _session(client, tok):
    u = _upload_judgment(client, tok)
    s = client.post("/api/workbench/sessions", headers=auth(tok),
                    json={"workflow_type": "judgment_analyzer", "upload_ids": [u["id"]]}).json()
    client.post(f"/api/workbench/sessions/{s['id']}/answers", headers=auth(tok),
                json={"answers": {"side": "complainant", "relief": "conviction u/s 138",
                                  "issue": "territorial jurisdiction", "court": "JMFC Hyderabad",
                                  "intended_use": "distinguish"}})
    return s


def _stub(quote_mode="exact"):
    def gen(wf, s, grounding, file_ctx="", **_kw):
        out = []
        for name in wf["sections"]:
            if name == "Key Quotable Passages":
                if quote_mode == "exact":
                    body = f'The court held: "{RATIO_SENTENCE}" [p.1]'
                elif quote_mode == "paraphrase":
                    body = ('"The offence is complete as soon as the cheque bounces and '
                            'the notice is ignored" [p.1]')
                elif quote_mode == "wrong_page":
                    body = f'"{RATIO_SENTENCE}" [p.7]'
                else:  # mixed: one exact + one paraphrase
                    body = (f'"{RATIO_SENTENCE}" [p.1]\n\n'
                            '"Jurisdiction lies wherever convenient for the payee" [p.1]')
            elif name == "Practical Application":
                body = ("This judgment remains good law and applies to the client's "
                        "forum question [p.1].")
            elif name in wf.get("file_sections", []):
                body = "Anchored in the judgment [p.1]."
            else:
                body = "Preparation note for counsel."
            out.append(f"## {name}\n{body}")
        out.append("Draft for advocate review. Verify facts, jurisdiction, limitation, "
                   "court rules, and latest case law before filing.")
        return "\n\n".join(out)
    return gen


def _generate(client, tok, s, mode, monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda x: "")
    monkeypatch.setattr(engine, "_llm_generate", _stub(mode))
    r = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _quotables(artifact):
    return next(x for x in artifact["sections"] if x["name"] == "Key Quotable Passages")


# ── The verbatim gate ─────────────────────────────────────────────────────────
def test_exact_quote_with_pinpoint_survives(client, monkeypatch):
    t = register_and_login(client, "ja1@firm.com")
    a = _generate(client, t, _session(client, t), "exact", monkeypatch)
    q = _quotables(a)
    assert q["blocked"] is False
    assert RATIO_SENTENCE in q["content"] and "[p.1]" in q["content"]


def test_paraphrase_as_quotation_is_removed_and_section_withheld(client, monkeypatch):
    t = register_and_login(client, "ja2@firm.com")
    a = _generate(client, t, _session(client, t), "paraphrase", monkeypatch)
    q = _quotables(a)
    assert q["blocked"] is True
    assert "withheld" in q["content"]                     # zero survivors → whole section held
    assert "bounces" not in q["content"]                  # the fake quote is gone


def test_exact_quote_on_wrong_page_fails_pinpoint(client, monkeypatch):
    t = register_and_login(client, "ja3@firm.com")
    a = _generate(client, t, _session(client, t), "wrong_page", monkeypatch)
    assert _quotables(a)["blocked"] is True               # pinpoint must be true too


def test_mixed_quotes_keep_the_real_one_and_strip_the_fake(client, monkeypatch):
    t = register_and_login(client, "ja4@firm.com")
    a = _generate(client, t, _session(client, t), "mixed", monkeypatch)
    q = _quotables(a)
    assert q["blocked"] is False
    assert RATIO_SENTENCE in q["content"]
    assert "wherever convenient" not in q["content"]
    assert engine.VERBATIM_REMOVED in q["content"]        # the strip stays visible


# ── Good-law discipline ───────────────────────────────────────────────────────
def test_good_law_assertion_is_scrubbed_and_caveated(client, monkeypatch):
    t = register_and_login(client, "ja5@firm.com")
    a = _generate(client, t, _session(client, t), "exact", monkeypatch)
    pa = next(x for x in a["sections"] if x["name"] == "Practical Application")
    assert "remains good law" not in pa["content"]
    assert "[good-law status unverified]" in pa["content"]
    assert "confirm treatment" in pa["content"].lower()   # caveat auto-appended


# ── Schema + grounding boundaries ─────────────────────────────────────────────
def test_all_thirteen_sections_render_judgment_grounded(client, monkeypatch):
    t = register_and_login(client, "ja6@firm.com")
    a = _generate(client, t, _session(client, t), "exact", monkeypatch)
    assert [x["name"] for x in a["sections"]] == SCHEMA
    ratio = next(x for x in a["sections"] if x["name"] == "Ratio Decidendi")
    assert ratio["grounding"] == "FILE"                   # grounded in the judgment itself
    assert a["review_status"] == "DRAFT_FOR_ADVOCATE_REVIEW"


# ── Kanoon pick ───────────────────────────────────────────────────────────────
def test_kanoon_pick_materialises_as_an_upload(client, monkeypatch):
    from app.ai import case_law
    monkeypatch.setattr(case_law, "fetch_document", lambda tid: {
        "tid": tid, "title": "Dashrath Rupsingh Rathod v. State of Maharashtra",
        "court": "Supreme Court of India", "date": "2014-08-01",
        "text": JUDGMENT_TEXT, "url": f"https://indiankanoon.org/doc/{tid}/"})
    t = register_and_login(client, "ja7@firm.com")
    r = client.post("/api/workbench/uploads/from-kanoon", headers=auth(t),
                    json={"tid": "https://indiankanoon.org/doc/110270205/"})
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["filename"].endswith(".txt") and "Dashrath" in u["filename"]
    assert u["page_count"] >= 1 and u["retention_policy"] == "scratch_7d"
    s = client.post("/api/workbench/sessions", headers=auth(t),
                    json={"workflow_type": "judgment_analyzer", "upload_ids": [u["id"]]})
    assert s.status_code == 201


def test_kanoon_pick_fails_closed_when_unavailable(client, monkeypatch):
    from app.ai import case_law
    monkeypatch.setattr(case_law, "fetch_document", lambda tid: None)
    t = register_and_login(client, "ja8@firm.com")
    r = client.post("/api/workbench/uploads/from-kanoon", headers=auth(t),
                    json={"tid": "12345"})
    assert r.status_code == 502
