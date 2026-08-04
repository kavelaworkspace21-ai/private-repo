"""
WB-03 — Case File Analysis (pack §5 W1 + §6 WB-03).

The LLM is stubbed (CI never calls a provider) — what's under test is the WB-03 wiring:
upload-bound sessions, FILE+LAW grounding per section, the [p.N] file-citation gate,
the prediction-probe refusal, banned-phrase scrubbing, and the review status.
"""
import io

import pytest

from tests.conftest import register_and_login, auth
from app.models.billing import KIND_RESEARCH
from app.services.workbench import engine
from app.services.workbench.workflows import WORKFLOWS

SCHEMA = WORKFLOWS["case_file_analysis"]["sections"]

FILE_TEXT = ("Complaint under section 138. The complainant Ramesh Kumar supplied cement "
             "under invoice INV-77. Cheque 445566 drawn on Canara Bank was returned unpaid "
             "on 12.06.2026 for insufficient funds. Statutory notice went on 15 July 2026.")

GROUNDING = ("VERIFIED STATUTORY TEXT\nSection 138 of the Negotiable Instruments Act, 1881 — "
             "Dishonour of cheque for insufficiency, etc., of funds in the account. [verbatim]")


def _upload(client, tok):
    r = client.post("/api/workbench/uploads", headers=auth(tok),
                    files={"file": ("case.txt", io.BytesIO(FILE_TEXT.encode()), "text/plain")})
    assert r.status_code == 201, r.text
    return r.json()


def _ready_session(client, tok, answers=None):
    u = _upload(client, tok)
    s = client.post("/api/workbench/sessions", headers=auth(tok),
                    json={"workflow_type": "case_file_analysis", "upload_ids": [u["id"]]}).json()
    a = answers or {"parties_side": "For the complainant Ramesh Kumar",
                    "court_stage": "JMFC Hyderabad, pre-cognizance",
                    "relief_context": "Prosecution u/s 138 and compensation"}
    client.post(f"/api/workbench/sessions/{s['id']}/answers", headers=auth(tok),
                json={"answers": a})
    return s


def _stub(mode="good"):
    """A 15-section generator: file sections carry [p.N], law sections cite s.138."""
    def gen(wf, s, grounding, file_ctx="", **_kw):
        out = []
        for name in wf["sections"]:
            if name == "Strengths of the Case" and mode == "good":
                body = ("The cheque and return memo are on record [p.1]. you will win "
                        "— counsel should still verify the notice dates [p.1].")
            elif name == "Facts Summary" and mode == "no_page_refs":
                body = "The complainant supplied cement and the cheque bounced."
            elif name in wf.get("file_sections", []):
                body = "Anchored in the record [p.1]: material drawn from the file."
            elif name == "Limitation Issues" and mode == "uncited_limitation":
                body = "The complaint appears within time under the applicable provision."
            elif name in wf["law_sections"]:
                body = ("Section 138 of the Negotiable Instruments Act governs; "
                        "its ingredients appear satisfied on the record [p.1].")
            else:
                body = "Qualitative preparation note tied to the stated facts."
            out.append(f"## {name}\n{body}")
        out.append("Draft for advocate review. Verify facts, jurisdiction, limitation, "
                   "court rules, and latest case law before filing.")
        return "\n\n".join(out)
    return gen


@pytest.fixture()
def stubbed(monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_llm_generate", _stub("good"))
    return monkeypatch


# ── Session creation rules ────────────────────────────────────────────────────
def test_analysis_requires_an_upload(client):
    t = register_and_login(client, "an1@firm.com")
    r = client.post("/api/workbench/sessions", headers=auth(t),
                    json={"workflow_type": "case_file_analysis"})
    assert r.status_code == 409 and "upload the case file first" in r.json()["detail"]


def test_judgment_analyzer_unlocked_but_needs_a_source(client):
    """WB-05 unlocked it; without a judgment attached it still refuses to start."""
    t = register_and_login(client, "an2@firm.com")
    r = client.post("/api/workbench/sessions", headers=auth(t),
                    json={"workflow_type": "judgment_analyzer"})
    assert r.status_code == 409 and "upload the case file first" in r.json()["detail"]


def test_foreign_upload_id_is_404(client):
    t1 = register_and_login(client, "an3@firm.com")
    t2 = register_and_login(client, "an4@firm.com")
    u = _upload(client, t1)
    r = client.post("/api/workbench/sessions", headers=auth(t2),
                    json={"workflow_type": "case_file_analysis", "upload_ids": [u["id"]]})
    assert r.status_code == 404


def test_session_lists_its_attached_upload(client):
    t = register_and_login(client, "an5@firm.com")
    s = _ready_session(client, t)
    got = client.get(f"/api/workbench/sessions/{s['id']}", headers=auth(t)).json()
    assert got["uploads"] and got["uploads"][0]["filename"] == "case.txt"


# ── The 15-section artifact under gates ───────────────────────────────────────
def test_full_analysis_all_sections_grounded_and_reviewed(client, stubbed):
    t = register_and_login(client, "an6@firm.com")
    s = _ready_session(client, t)
    g = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t))
    assert g.status_code == 200, g.text
    a = g.json()
    assert [x["name"] for x in a["sections"]] == SCHEMA          # all 15, in order
    tags = {x["name"]: x["grounding"] for x in a["sections"]}
    assert tags["Facts Summary"] == "FILE"
    assert tags["Limitation Issues"] == "LAW"
    assert tags["Jurisdiction Issues"] == "LAW"
    assert a["citations"] == ["138"]                             # verified against grounding
    assert a["review_status"] == "DRAFT_FOR_ADVOCATE_REVIEW"
    used = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    assert used == 1


def test_banned_phrase_is_scrubbed_from_sections(client, stubbed):
    t = register_and_login(client, "an7@firm.com")
    s = _ready_session(client, t)
    a = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t)).json()
    strengths = next(x for x in a["sections"] if x["name"] == "Strengths of the Case")
    assert "you will win" not in strengths["content"].lower()
    assert "[removed: non-compliant claim]" in strengths["content"]


def test_uncited_limitation_section_is_withheld(client, monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_llm_generate", _stub("uncited_limitation"))
    t = register_and_login(client, "an8@firm.com")
    s = _ready_session(client, t)
    a = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t)).json()
    lim = next(x for x in a["sections"] if x["name"] == "Limitation Issues")
    assert lim["blocked"] is True and "withheld" in lim["content"]
    sess = client.get(f"/api/workbench/sessions/{s['id']}", headers=auth(t)).json()
    assert sess["state"] == "COMPLETE"        # other law sections passed — not a full refusal


def test_file_section_without_page_refs_is_withheld(client, monkeypatch):
    monkeypatch.setattr(engine, "_grounding_for", lambda s: GROUNDING)
    monkeypatch.setattr(engine, "_llm_generate", _stub("no_page_refs"))
    t = register_and_login(client, "an9@firm.com")
    s = _ready_session(client, t)
    a = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t)).json()
    facts = next(x for x in a["sections"] if x["name"] == "Facts Summary")
    assert facts["blocked"] is True
    assert "page references" in facts["content"]


# ── No prediction, ever ───────────────────────────────────────────────────────
def test_will_i_win_probe_is_refused_before_any_cost(client, stubbed):
    t = register_and_login(client, "an10@firm.com")
    s = _ready_session(client, t, answers={
        "parties_side": "For the complainant",
        "court_stage": "JMFC Hyderabad",
        "relief_context": "Tell me — will I win this case?"})
    r = client.post(f"/api/workbench/sessions/{s['id']}/generate", headers=auth(t))
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["error"] == "prediction_refused"
    assert "does not predict" in d["message"]
    used = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    assert used == 0                                             # refusal costs nothing
