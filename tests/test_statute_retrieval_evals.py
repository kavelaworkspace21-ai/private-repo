"""Statute-retrieval eval runner — the expanded corpus's high-stakes provisions.

Every case must serve the RIGHT verbatim provision (content keyword, not key presence) and
fire the repeal flag exactly where required. 100% must pass (Gate-C support; the live-LLM
graded eval remains the senior advocate's G8 call, never self-certified)."""
import pytest

from app.ai.evals.statute_retrieval_eval_set import RETRIEVAL_EVAL_CASES
from app.ai.rag import retrieve_by_section


def _corpus_available() -> bool:
    try:
        from app.ai.vector_store import get_collection
        return get_collection().count() > 0
    except Exception:
        return False


requires_corpus = pytest.mark.skipif(not _corpus_available(), reason="legal corpus not present")


@requires_corpus
@pytest.mark.parametrize("case_id,query,keyword,expect_repealed",
                         RETRIEVAL_EVAL_CASES,
                         ids=[c[0] for c in RETRIEVAL_EVAL_CASES])
def test_high_stakes_retrieval(case_id, query, keyword, expect_repealed):
    out = retrieve_by_section(query) or ""
    assert out, f"{case_id}: deterministic lookup returned nothing"
    assert keyword.lower() in out.lower(), (
        f"{case_id}: expected content keyword {keyword!r} in the served provision")
    if expect_repealed:
        assert "REPEALED" in out, f"{case_id}: repeal warning missing for a repealed statute"
    else:
        assert "REPEALED" not in out, f"{case_id}: false repeal warning on an in-force statute"


@requires_corpus
def test_eval_set_pass_rate_is_100_percent():
    failures = []
    for case_id, query, keyword, expect_repealed in RETRIEVAL_EVAL_CASES:
        out = retrieve_by_section(query) or ""
        ok = (bool(out) and keyword.lower() in out.lower()
              and (("REPEALED" in out) is expect_repealed))
        if not ok:
            failures.append(case_id)
    assert not failures, f"retrieval eval failures: {failures}"
