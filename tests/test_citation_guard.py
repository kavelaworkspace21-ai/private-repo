"""Phase 4 — deterministic citation-resolution guard (app/ai/citation_guard.py).

The gate: every statutory citation an answer displays must resolve to a real corpus section; a
fabricated section (right act, non-existent number) is caught. Runs against the real corpus (like
the retrieval evals).
"""
from app.ai.citation_guard import verify_citations, integrity_event


def test_real_citations_all_resolve():
    text = ("Under Section 138 of the Negotiable Instruments Act and Article 21 of the "
            "Constitution, and Section 4 of the Income-tax Act 2025, the position is clear.")
    r = verify_citations(text)
    assert r["all_resolved"] is True
    assert not r["unresolved"]
    assert len(r["resolved"]) == 3


def test_fabricated_section_is_flagged():
    r = verify_citations("As held, Section 9999 of the Negotiable Instruments Act bars this.")
    assert r["all_resolved"] is False
    assert any(c["section"] == "9999" for c in r["unresolved"])


def test_ita2025_attributes_to_the_2025_act():
    r = verify_citations("Section 4 of the Income-tax Act 2025 charges tax on the tax year.")
    assert r["all_resolved"] is True
    assert r["resolved"][0]["act"] == "Income-tax Act, 2025"


def test_limitation_article_resolves_via_schedule():
    r = verify_citations("See Article 5 of the Limitation Act for the limitation period.")
    assert r["all_resolved"] is True
    assert r["resolved"] and r["resolved"][0]["act"] == "Limitation Act, 1963"


def test_section_without_a_named_act_is_unverifiable_not_fabricated():
    r = verify_citations("The section 5 requirement is procedural.")
    # a bare number with no nearby act can't be checked — it must NOT be called fabricated
    assert r["all_resolved"] is True
    assert any(c["section"] == "5" for c in r["unverifiable"])


def test_integrity_event_none_when_clean():
    # the answer-path helper: clean answer → no signal
    assert integrity_event("Section 138 of the Negotiable Instruments Act applies.") is None


def test_integrity_event_flags_fabrication():
    ci = integrity_event("Section 9999 of the Negotiable Instruments Act bars this.")
    assert ci is not None and ci["ok"] is False
    assert any("9999" in f for f in ci["fabricated"])


def test_mixed_real_and_fabricated():
    text = ("Section 138 of the Negotiable Instruments Act applies, but Section 8888 of the "
            "Negotiable Instruments Act does not exist.")
    r = verify_citations(text)
    assert r["all_resolved"] is False
    assert any(c["section"] == "138" for c in r["resolved"])
    assert any(c["section"] == "8888" for c in r["unresolved"])
