"""LSAI-LEGAL-22 — the pre-publish lock is engaged (fail-closed) until human gates are signed."""
from app.legal_config import (
    public_launch_blocked, public_launch_status, LAUNCH_GATES, assert_prohibited_disabled,
)


def test_public_launch_is_blocked_by_default():
    assert public_launch_blocked() is True


def test_all_human_gates_open_by_default():
    # Code must never self-certify a human gate.
    assert all(v is False for v in LAUNCH_GATES.values())
    status = public_launch_status()
    assert status["blocked"] is True
    assert set(status["pending"]) == set(LAUNCH_GATES.keys())


def test_core_human_gates_present():
    for g in ("G1_corpus_authenticity", "G6_privacy_review",
              "G7_security_review", "G8_senior_advocate_signoff"):
        assert g in LAUNCH_GATES


def test_prohibited_features_stay_disabled():
    # Must not raise — all prohibited AI features remain off.
    assert_prohibited_disabled()
