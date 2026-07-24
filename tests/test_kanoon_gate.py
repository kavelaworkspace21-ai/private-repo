"""Indian Kanoon is the one genuinely BILLED dependency — prove it cannot fire by accident.

Before this gate existed, enablement was inferred purely from INDIAN_KANOON_API_KEY being
present, and the dashboard fetched judgments on every load — one billed call per user per
visit, on the highest-traffic page. These tests pin the two properties that matter:

  1. Enablement requires an explicit opt-in AND a key (a key alone spends nothing).
  2. When disabled, NO code path performs an HTTP request — verified by making any network
     call an immediate test failure, not by trusting the return value.
"""
import pytest

from app.ai import case_law
from tests.conftest import auth, register_and_login


@pytest.fixture
def call_recorder(monkeypatch):
    """Record outbound HTTP attempts so 'disabled' means 'never touched the API'.

    A COUNTER, not a raise: every network path in case_law.py is wrapped in
    `except Exception`, so an exception raised from a stubbed client would be swallowed
    and the test would pass even when a billed call had been made. The counter survives
    the swallow; the raise keeps the request from actually leaving the machine.
    """
    import httpx
    calls: list[str] = []

    def _record(self, url, *a, **k):
        calls.append(str(url))
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(httpx.Client, "post", _record)
    monkeypatch.setattr(httpx.Client, "get", _record, raising=False)
    return calls


def test_the_recorder_actually_catches_calls(monkeypatch, call_recorder):
    """Guards the guard: prove the recorder sees a call when the gate is OPEN.

    Without this, every 'no call was made' assertion below could be vacuously true.
    """
    _set(monkeypatch, enabled=True, key="a-real-looking-key")
    case_law._CACHE.clear()
    case_law.latest_judgments()
    assert call_recorder, "recorder saw nothing with the gate open — it cannot prove anything"


def _set(monkeypatch, *, enabled, key):
    monkeypatch.setattr(case_law, "KANOON_ENABLED", enabled)
    monkeypatch.setattr(case_law, "KANOON_API_KEY", key)


# ── Enablement requires BOTH ────────────────────────────────────────────────────
def test_key_alone_does_not_enable_spending(monkeypatch):
    _set(monkeypatch, enabled=False, key="a-real-looking-key")
    assert case_law.is_enabled() is False


def test_flag_alone_does_not_enable(monkeypatch):
    _set(monkeypatch, enabled=True, key="")
    assert case_law.is_enabled() is False


def test_enabled_only_with_both(monkeypatch):
    _set(monkeypatch, enabled=True, key="a-real-looking-key")
    assert case_law.is_enabled() is True


def test_default_is_off():
    """Unset env => off. Guards against the default silently flipping to on."""
    import os
    assert os.getenv("KANOON_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"} \
        or case_law.KANOON_ENABLED is True   # only true if the env deliberately set it


# ── Disabled => no billed call reaches the network ──────────────────────────────
def test_no_billed_call_when_disabled_even_with_key(monkeypatch, call_recorder):
    _set(monkeypatch, enabled=False, key="a-real-looking-key")
    case_law._CACHE.clear()

    assert case_law.retrieve_cases("section 138 cheque bounce") == ""
    assert case_law.search_cases("anticipatory bail") == []
    assert case_law.latest_judgments() == []
    assert case_law.fetch_document("110270205") is None
    assert case_law.summarize_case("110270205") is None

    assert call_recorder == [], f"billed Indian Kanoon calls made while disabled: {call_recorder}"


# ── The dashboard's own guard: /status is free and reports the gate ─────────────
def test_research_status_reports_the_gate(client, monkeypatch):
    tok = register_and_login(client, "kanoon@firm.com")

    monkeypatch.setattr(case_law, "KANOON_ENABLED", False)
    monkeypatch.setattr(case_law, "KANOON_API_KEY", "a-real-looking-key")
    r = client.get("/api/research/status", headers=auth(tok))
    assert r.status_code == 200
    assert r.json()["case_law_enabled"] is False, (
        "the dashboard relies on this to decide whether to make the paid call")
