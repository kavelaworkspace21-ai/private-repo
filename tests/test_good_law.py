"""
"Is it still good law?" trust signal. We never claim a judgment is good law (treatment is
unverifiable from the basic API); every case result must carry the unverified caveat.
"""
from app.ai import case_law
from app.routers.research import CaseCard, CaseSummary


def test_caveat_warns_about_overruled():
    c = case_law.GOOD_LAW_CAVEAT.lower()
    assert "overrul" in c and "not verified" in c


def test_card_carries_good_law_caveat():
    card = case_law._card_from_doc({
        "tid": 123, "title": "X vs Y", "docsource": "Supreme Court of India",
        "publishdate": "2020-01-01", "numcitedby": 10, "headline": "snippet",
    })
    assert card["good_law"] == "unverified"
    assert card["good_law_caveat"] == case_law.GOOD_LAW_CAVEAT
    assert card["url"] == "https://indiankanoon.org/doc/123/"


def test_card_never_claims_good_law():
    card = case_law._card_from_doc({"tid": 1, "title": "A vs B"})
    assert card["good_law"] != "yes" and card["good_law"] != "good"


def test_api_schemas_default_to_unverified():
    cc = CaseCard(title="t", court="c", date="d", citation="", cited_by="0", snippet="", url="u")
    assert cc.good_law == "unverified"
    cs = CaseSummary(title="t", court="c", date="d", cited_by="0", summary="s", url="u",
                     disclaimer="d")
    assert cs.good_law == "unverified"
