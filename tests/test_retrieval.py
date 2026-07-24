"""Tests for the deterministic retrieval helpers added for section-precise grounding.

Pure-logic tests (act detection, section parsing) always run. Integration tests that
hit the real ChromaDB corpus skip cleanly when the corpus isn't present (e.g. fresh CI).
"""
import pytest

from app.ai.rag import (
    _detect_act,
    _SECTION_RE,
    retrieve_by_section,
    retrieve_by_title_keyword,
)


# ── Pure logic (no corpus needed) ─────────────────────────────────────────────

def test_detect_act_aliases():
    assert _detect_act("what does section 138 of the negotiable instruments act say") == \
        "Negotiable Instruments Act, 1881"
    assert _detect_act("punishment for theft under bns") == "Bharatiya Nyaya Sanhita, 2023"
    assert _detect_act("section 420 ipc cheating") == "Indian Penal Code, 1860"
    assert _detect_act("crpc bail provisions") == "Code of Criminal Procedure, 1973"


def test_detect_act_income_tax_disambiguation():
    """Bare "income tax" stays on the repealed 1961 Act (IPC→BNS precedent — the currency
    layer flags it); any 2025-qualified form must win via longest-alias-match, and the
    IT Act 2000 / IT Rules 2026 neighbours must not be hijacked."""
    assert _detect_act("section 80c of the income-tax act") == "Income-tax Act, 1961"
    assert _detect_act("section 4 of the income-tax act 2025") == "Income-tax Act, 2025"
    assert _detect_act("ita 2025 section 536") == "Income-tax Act, 2025"
    assert _detect_act("it act 2025 charge of income-tax") == "Income-tax Act, 2025"
    assert _detect_act("section 66a of the it act") == "Information Technology Act, 2000"
    assert _detect_act("rule 12 of the income tax rules") == "Income-tax Rules, 2026"


def test_detect_act_none_when_no_act_named():
    assert _detect_act("what is the punishment for cheating") is None
    assert _detect_act("hello, how are you") is None


def _nums(q):
    # _SECTION_RE now captures (keyword, number) so intent (article vs section) is known;
    # this helper pulls just the numbers for the extraction assertions.
    return [t[1] for t in _SECTION_RE.findall(q)]


def test_section_regex_extracts_numbers_cleanly():
    assert _nums("What does Section 138 of the Act say?") == ["138"]
    assert _nums("offence u/s 420 IPC and s.138A NI Act") == ["420", "138A"]
    assert _nums("explain bail") == []
    # the keyword is captured so "Article" vs "Section" intent is available downstream
    kinds = [t[0].lower() for t in _SECTION_RE.findall("Article 5 vs Section 5")]
    assert kinds[0].startswith("art") and kinds[1].startswith("s")


def test_format_citation_nomenclature_and_no_double_year():
    """C-02: a copy-ready citation built only from stored provenance. The Constitution's
    provisions are ARTICLES (never 's.'); corpus act titles already carry the year, so it
    must not be doubled; unverified provisions must say so (never over-claim)."""
    from app.ai.rag import format_citation
    con = format_citation("The Constitution of India", "1950", "21",
                          "Protection of life and personal liberty", page="28", verified=True)
    assert con.startswith("Art.21, Constitution of India")
    assert "1950" not in con                      # Constitution cited year-less by convention
    assert "p.28" in con and "indiacode.nic.in" in con

    ni = format_citation("Negotiable Instruments Act, 1881", "1881", "138",
                         "Dishonour of cheque", page="42", verified=True)
    assert ni.startswith("s.138, Negotiable Instruments Act, 1881")
    assert "1881, 1881" not in ni                  # year already in the title — not doubled
    assert "p.42" in ni

    unv = format_citation("Right to Information Act, 2005", "2005", "6",
                          "Request for information", verified=False)
    assert "heading only" in unv and "indiacode.nic.in" in unv


def test_format_citation_flags_repealed_statutes():
    """P2 currency rule: a repealed provision is NEVER cited as if in force. The flag names
    the successor when known (IPC→BNS, ITA 1961→ITA 2025)."""
    from app.ai.rag import format_citation
    ipc = format_citation("Indian Penal Code, 1860", "1860", "420", "Cheating",
                          page="88", verified=True,
                          status="repealed", repealed_by="Bharatiya Nyaya Sanhita, 2023")
    assert "[REPEALED — now see Bharatiya Nyaya Sanhita, 2023]" in ipc
    ita = format_citation("Income-tax Act, 1961", "1961", "139", "Return of income",
                          verified=True, status="repealed", repealed_by="Income-tax Act, 2025")
    assert "now see Income-tax Act, 2025" in ita
    # in-force acts carry NO repeal noise
    ni = format_citation("Negotiable Instruments Act, 1881", "1881", "138",
                         "Dishonour of cheque", verified=True, status="in_force")
    assert "REPEALED" not in ni


def test_section_regex_matches_constitution_articles():
    """The Constitution is cited as 'Article N', not 'Section N' — the deterministic path
    must recognise it, or the citation-grade article ingest is unreachable."""
    assert _nums("What does Article 21 of the Constitution say?") == ["21"]
    assert _nums("Art. 300A and article 32 of the Constitution") == ["300A", "32"]
    # 'art'/'article' inside ordinary words must NOT be misread as an article citation
    assert _nums("let's start 5 drafts for the arts council") == []
    assert _nums("restart 3 times") == []


# ── Integration with the real corpus (skips if absent) ────────────────────────

def _corpus_available() -> bool:
    try:
        from app.ai.vector_store import get_collection
        return get_collection().count() > 0
    except Exception:
        return False


requires_corpus = pytest.mark.skipif(not _corpus_available(), reason="legal corpus not present")


@requires_corpus
def test_retrieve_by_section_returns_exact_verbatim():
    out = retrieve_by_section("What does Section 138 of the Negotiable Instruments Act deal with?").lower()
    assert "138" in out
    assert "negotiable instruments" in out
    assert "cheque" in out            # s.138 is dishonour of cheque — proves it's the real text
    assert "verbatim text" in out      # came through the verified path, not a heading


@requires_corpus
def test_repealed_act_lookup_carries_repeal_warning():
    """Deterministic lookup of a repealed act's section must include the repeal warning in the
    grounding block, so the model states it (IPC s.420 → BNS pointer)."""
    out = retrieve_by_section("Section 420 of the Indian Penal Code")
    assert "cheat" in out.lower()                       # verbatim text still served
    assert "REPEALED" in out                             # warning present
    assert "Bharatiya Nyaya Sanhita" in out              # successor named
    # and an in-force act must NOT get the warning
    ni = retrieve_by_section("Section 138 of the Negotiable Instruments Act")
    assert "REPEALED" not in ni


@requires_corpus
def test_retrieve_constitution_article_verbatim():
    """Article 21 must return its real provision ('Protection of life and personal liberty'),
    proving the schedule-aware ingest put the correct article — not a Schedule paragraph —
    in the corpus, and that the deterministic path reaches it via 'Article N'."""
    out = retrieve_by_section("What does Article 21 of the Constitution guarantee?").lower()
    assert "21" in out and "constitution" in out
    assert "life" in out and "personal liberty" in out
    assert "amendment of the schedule" not in out   # the collision that was averted
    assert "verbatim text" in out                     # came through the verified path


@requires_corpus
def test_structured_labels_constitution_as_article_with_pinpoint():
    """C-02: the Sources footer draws from retrieve_structured — Constitution provisions must
    carry the 'Art.' abbreviation and a page pinpoint, and a paste-ready citation string."""
    from app.ai.rag import retrieve_structured
    rows = retrieve_structured("Article 21 of the Constitution protection of life", top_k=5)
    con = [r for r in rows if "constitution" in r["act"].lower()]
    assert con, "expected a Constitution provision in structured results"
    r = con[0]
    assert r["abbr"] == "Art." and r["unit"] == "Article"
    assert r["citation"].startswith("Art.")
    assert r["page"]                                  # pinpoint present for verified articles


@requires_corpus
def test_seventh_schedule_entries_are_retrievable_by_competence_query():
    """The Seventh Schedule's legislative Lists must surface for competence questions
    ('under which list does X fall'), citing the correct List + entry verbatim."""
    from app.ai.rag import retrieve_structured
    rows = retrieve_structured(
        "under which list of the Seventh Schedule does tax on agricultural income fall", top_k=10)
    hit = [r for r in rows if "agricultural income" in r["title"].lower()]
    assert hit, "State List Entry 46 (agricultural income) not retrieved"
    assert str(hit[0]["section"]).startswith("Sch7")
    assert "State List, Entry 46" in hit[0]["citation"]


@requires_corpus
def test_retrieve_by_section_needs_an_act():
    # A bare section number with no Act named is ambiguous → no deterministic hit.
    assert retrieve_by_section("what does section 138 say") == ""


@requires_corpus
def test_title_keyword_leads_with_base_offence_not_variant():
    out = retrieve_by_title_keyword("punishment for cheating under the Bharatiya Nyaya Sanhita")
    assert "318" in out                       # base offence "Cheating"
    assert "Cheating" in out
    # exact-only selection means the qualified variant must NOT be injected
    assert "personation" not in out.lower()   # s.319 "Cheating by personation" excluded


@requires_corpus
def test_title_keyword_requires_named_act():
    assert retrieve_by_title_keyword("what is the punishment for cheating") == ""


# ── Acts ingested this session: alias map + Schedule-split parser ─────────────

def test_detect_act_newly_added_acts():
    cases = {
        "section 54 of the transfer of property act": "Transfer of Property Act, 1882",
        "specific relief act injunction": "Specific Relief Act, 1963",
        "dissolution under the indian partnership act": "Indian Partnership Act, 1932",
        "sale of goods act implied conditions": "Sale of Goods Act, 1930",
        "hindu succession act coparcener": "Hindu Succession Act, 1956",
        "domestic violence act section 3": "Protection of Women from Domestic Violence Act, 2005",
        "indian succession act will": "Indian Succession Act, 1925",
        "pocso section 4": "Protection of Children from Sexual Offences Act, 2012",
        "rera section 18": "Real Estate (Regulation and Development) Act, 2016",
        "insolvency and bankruptcy code section 7": "Insolvency and Bankruptcy Code, 2016",
        "indian easements act section 4": "Indian Easements Act, 1882",
        "limitation act section 5": "Limitation Act, 1963",
    }
    for q, expect in cases.items():
        assert _detect_act(q) == expect, q
    # SARFAESI long title
    assert _detect_act("sarfaesi section 13").startswith("Securitisation and Reconstruction")


def test_segment_with_schedule_splits_body_and_articles():
    """Body sections stay 'N'; Schedule articles become 'Sch.N' (so they never collide)."""
    from app.ai.ingest_statutes import _segment_with_schedule
    pages = [
        "1. Short title.—This Act may be called the Test Act.\n"
        "2. Definitions.—In this Act, words have meanings.",
        "THE SCHEDULE\n"
        "1. For suits on money. Three years. When the money is due.\n"
        "2. For other suits. One year. When the right accrues.",
    ]
    secs = _segment_with_schedule(pages)
    body = [s["num"] for s in secs if not str(s["num"]).startswith("Sch.")]
    arts = [s["num"] for s in secs if str(s["num"]).startswith("Sch.")]
    assert body == ["1", "2"]
    assert arts == ["Sch.1", "Sch.2"]
    assert next(s for s in secs if s["num"] == "Sch.1")["title"].startswith("Schedule, Article 1")


@requires_corpus
def test_new_acts_retrievable_verbatim():
    tp = retrieve_by_section("Section 54 of the Transfer of Property Act").lower()
    assert "verbatim text" in tp and "transfer of ownership" in tp
    dv = retrieve_by_section("Section 3 of the Protection of Women from Domestic Violence Act").lower()
    assert "domestic violence" in dv
