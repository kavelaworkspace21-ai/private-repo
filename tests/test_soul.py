"""
THE SOUL — hard-wired, fail-closed guard. These tests prove the kill-switch actually fires:
the system must REFUSE TO RUN if the safety doctrine is disabled or tampered with.
"""
import pytest

import app.legal_config as lc
import app.ai.safety as sfty
from app.soul import assert_soul_intact, check_soul, SoulViolation


def test_soul_intact_on_real_system():
    # The shipped, untampered system must pass.
    assert check_soul() == []
    assert_soul_intact()  # no raise


def test_soul_fails_if_prohibited_feature_enabled(monkeypatch):
    monkeypatch.setitem(lc.PROHIBITED_FEATURES, "case_prediction", True)
    with pytest.raises(SoulViolation):
        assert_soul_intact()


def test_soul_fails_if_identity_gate_flipped(monkeypatch):
    # Turning Juriscite into a public AI-lawyer is a soul violation.
    monkeypatch.setattr(lc, "PUBLIC_AI_LAWYER", True)
    with pytest.raises(SoulViolation):
        assert_soul_intact()


def test_soul_fails_if_banned_phrase_gate_disabled(monkeypatch):
    monkeypatch.setattr(sfty, "_BANNED_RE", [])
    with pytest.raises(SoulViolation):
        assert_soul_intact()


def test_soul_fails_if_no_source_gate_broken(monkeypatch):
    monkeypatch.setattr(sfty, "is_answerable", lambda ctx: True)  # pretend empty context is answerable
    with pytest.raises(SoulViolation):
        assert_soul_intact()


def test_soul_fails_if_unlawful_screen_broken(monkeypatch):
    monkeypatch.setattr(sfty, "screen_request_intent", lambda text: None)  # never refuses
    with pytest.raises(SoulViolation):
        assert_soul_intact()


def test_health_reports_soul_intact(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["soul"] == "intact"
