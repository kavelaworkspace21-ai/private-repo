"""Library search must understand the words advocates actually use.

The statutes never say "anticipatory bail" — CrPC s.438 and BNSS s.482 are both headed
"Direction for grant of bail to person apprehending arrest". Nor do they say "FIR"; that is
"Information in cognizable cases" (CrPC s.154 / BNSS s.173).

This gap was invisible until 2026-07-30 for an instructive reason. `test_search_finds_sections`
searched for "anticipatory bail" and passed — because the phrase occurred inside CrPC s.38's
CONTAMINATED text, an amendment clause quoting s.438 that had overwritten the real provision.
Repairing the corpus removed the phrase and the test failed. It had been green because the
corpus was wrong, and it was testing the contamination rather than the feature.

So these tests assert the mapping resolves to REAL provisions in BOTH the old Code and its
2023 successor, and that the expansion cannot fire on unrelated words.
"""
from app.services import library


def _nums(hits, act_id):
    return {h["num"] for h in hits if h["act_id"] == act_id}


def test_anticipatory_bail_finds_the_provision_in_both_codes():
    hits = library.search("anticipatory bail", limit=200)
    assert hits, "the commonest name for CrPC s.438 must find something"
    assert "438" in _nums(hits, "crpc_1973"), "CrPC s.438 not found"
    assert "482" in _nums(hits, "bnss_2023"), "BNSS s.482 (the successor) not found"


def test_fir_finds_information_in_cognizable_cases():
    hits = library.search("FIR", limit=200)
    assert "154" in _nums(hits, "crpc_1973"), "CrPC s.154 not found"
    assert "173" in _nums(hits, "bnss_2023"), "BNSS s.173 not found"


def test_first_information_report_spelled_out_works_too():
    hits = library.search("first information report", limit=200)
    assert "154" in _nums(hits, "crpc_1973")


def test_expansion_is_exact_match_not_substring():
    """"fir" must not be triggered by "firm", "confirm" or "first"."""
    hits = library.search("firm", limit=200)
    assert "154" not in _nums(hits, "crpc_1973"), (
        "the 'fir' alias fired on 'firm' — expansion must match the whole query only")


def test_ordinary_queries_are_unaffected():
    hits = library.search("dowry death", limit=200)
    assert hits, "a literal statutory phrase must still match directly"


def test_the_aliases_point_at_wording_that_actually_exists():
    """An alias whose target phrase has vanished from the corpus is silently useless."""
    for phrase, targets in library._COLLOQUIAL_TERMS.items():
        for target in targets:
            assert library.search(target, limit=5), (
                f"alias {phrase!r} expands to {target!r}, which matches nothing in the "
                f"corpus — the mapping is stale")
