"""LSAI-LEGAL-20 — run the deterministic legal-AI safety eval set; 100% must pass (no-hallucination)."""
import pytest

from app.ai.evals.legal_eval_set import EVAL_CASES, KINDS
from app.ai.safety import (
    is_answerable, enforce_citations, contains_banned_phrase, screen_request_intent,
)


def _evaluate(case: dict) -> bool:
    kind = case["kind"]
    if kind == "answerability":
        return is_answerable(case["context"]) is case["expect_answerable"]
    if kind == "citation":
        _, bad = enforce_citations(case["answer"], case["context"])
        return bool(bad) is case["expect_flagged"]
    if kind == "banned":
        return contains_banned_phrase(case["answer"]) is case["expect_banned"]
    if kind == "intent":
        refused = screen_request_intent(case["question"]) is not None
        return refused is case["expect_refused"]
    raise AssertionError(f"unknown kind: {kind}")


@pytest.mark.parametrize("case", EVAL_CASES, ids=[c["id"] for c in EVAL_CASES])
def test_each_eval_case(case):
    assert _evaluate(case), f"eval case failed: {case['id']}"


def test_eval_set_covers_every_safety_kind():
    assert {c["kind"] for c in EVAL_CASES} == KINDS


def test_eval_pass_rate_is_100_percent():
    passed = sum(1 for c in EVAL_CASES if _evaluate(c))
    assert passed == len(EVAL_CASES), f"{passed}/{len(EVAL_CASES)} eval cases passed (must be 100%)"
