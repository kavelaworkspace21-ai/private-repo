"""Phase 5 (cont.) — honest currency for un-fetchable drift sources.

The rule: an automated drift check that ERRORS (WAF) or is SKIPPED (landing page) proves
nothing about currency and must NEVER be reported as 'current'. It falls back to a valid
human verification, or is reported UNVERIFIED.
"""
import app.ai.corpus_updates as cu


def test_currency_automated_states():
    assert cu._currency("x", "unchanged", {})["state"] == "verified_current_automated"
    assert cu._currency("x", "UPDATED_UPSTREAM", {})["state"] == "drift_detected"


def test_errored_or_skipped_source_is_unverified_without_manual():
    assert cu._currency("income_tax_2025", "error", {})["state"] == "UNVERIFIED"
    assert cu._currency("income_tax_rules_2026", "skipped_no_pdf", {})["state"] == "UNVERIFIED"


def test_valid_manual_verification_makes_it_current():
    manual = {"income_tax_2025": {"last_verified_at": "2026-07-21", "reviewer": "Adv. X",
                                  "next_review": "2099-01-01"}}
    c = cu._currency("income_tax_2025", "error", manual)
    assert c["state"] == "manually_verified" and c["reviewer"] == "Adv. X"


def test_stale_manual_verification_is_unverified():
    manual = {"a": {"last_verified_at": "2020-01-01", "next_review": "2020-06-01"}}
    assert cu._currency("a", "error", manual)["state"] == "UNVERIFIED"


def test_manual_stale_rules():
    assert cu._manual_stale({}) is True                                                   # empty
    assert cu._manual_stale({"last_verified_at": "2026-01-01"}) is False                  # no next_review
    assert cu._manual_stale({"last_verified_at": "2026-01-01", "next_review": "2099-01-01"}) is False
    assert cu._manual_stale({"last_verified_at": "2026-01-01", "next_review": "2000-01-01"}) is True


def test_seed_records_are_pending_not_fabricated():
    """The committed manual_verifications.json must NOT claim a verification the agent can't make."""
    m = cu.load_manual_verifications()
    for act in ("income_tax_2025", "income_tax_rules_2026"):
        assert act in m
        assert m[act]["last_verified_at"] is None, "seed must be PENDING, never a fabricated sign-off"


def test_record_manual_verification_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cu, "MANUAL_VERIF_PATH", tmp_path / "manual.json")
    rec = cu.record_manual_verification("income_tax_2025", reviewer="Adv. Y", next_review_days=90)
    assert rec["reviewer"] == "Adv. Y" and rec["last_verified_at"]
    loaded = cu.load_manual_verifications()
    assert cu._currency("income_tax_2025", "error", loaded)["state"] == "manually_verified"


def test_check_upstream_attaches_currency_and_never_calls_errored_current(tmp_path, monkeypatch):
    monkeypatch.setattr(cu, "CHECK_RESULT_PATH", tmp_path / "upstream.json")

    def boom(url):
        raise RuntimeError("WAF 403 Forbidden")

    out = cu.check_upstream(act_ids=["income_tax_2025"], fetcher=boom)
    r = out["results"]["income_tax_2025"]
    assert r["status"] in ("error", "skipped_no_pdf")
    assert r["currency"]["state"] == "UNVERIFIED"
    assert out["summary"]["unverified_currency"] >= 1
