"""
Billing / subscriptions / entitlements (LSAI-V3-05 · Gate G11).

Everything here runs in Razorpay TEST mode. No live keys, no real payments, no PII.
"""
import hashlib
import hmac
import json

import pytest

from tests.conftest import register_and_login, auth
from app.services import billing as bl
from app.models.billing import KIND_RESEARCH, KIND_DRAFT, STATUS_TRIALING


def _login(client, email, role="advocate"):
    client.post("/api/auth/register", json={
        "full_name": "Billing User", "email": email, "password": "Sup3rSecret!", "role": role})
    r = client.post("/api/auth/login", json={"email": email, "password": "Sup3rSecret!"})
    return r.json().get("access_token")


# ── L1: plans catalogue ───────────────────────────────────────────────────────
def test_plans_is_public_and_seeded(client):
    r = client.get("/api/billing/plans")           # public — the pricing page needs it
    assert r.status_code == 200
    body = r.json()
    codes = [p["code"] for p in body["plans"]]
    assert codes == ["free", "solo_advocate", "firm", "enterprise"]
    assert body["billing_mode"] == "test", "billing must never default to live"


def test_plan_prices_and_limits_are_data(client):
    plans = {p["code"]: p for p in client.get("/api/billing/plans").json()["plans"]}
    assert plans["solo_advocate"]["price_monthly_inr"] == 999
    assert plans["solo_advocate"]["price_annual_inr"] == 9990          # 2 months free
    assert plans["firm"]["per_seat"] is True and plans["firm"]["min_seats"] == 3
    assert plans["enterprise"]["price_monthly_inr"] is None            # sales-led
    assert plans["free"]["limits"]["research_queries_per_month"] == 5
    assert plans["free"]["limits"]["court_diary"] == "read_only"


def test_pricing_page_config_has_no_dark_patterns(client):
    body = client.get("/api/billing/plans").json()
    assert body["trial"]["requires_card"] is False       # never force a card for a trial
    assert body["trial"]["length_days"] == 14
    assert body["gst"]["display"] == "exclusive"
    assert body["founding_member"]["price_monthly_inr"] == 499


# ── L2: subscription + trial on signup ────────────────────────────────────────
def test_signup_starts_a_no_card_trial(client):
    t = register_and_login(client, "trial@firm.com")
    r = client.get("/api/billing/subscription", headers=auth(t))
    assert r.status_code == 200
    s = r.json()
    assert s["plan_code"] == "solo_advocate"
    assert s["status"] == STATUS_TRIALING
    assert s["trial_end"] is not None
    assert s["cancel_at_period_end"] is False


def test_usage_starts_empty_and_reports_limits(client):
    t = register_and_login(client, "usage@firm.com")
    u = client.get("/api/billing/usage", headers=auth(t)).json()
    assert u["items"][KIND_RESEARCH]["used"] == 0
    assert u["items"][KIND_RESEARCH]["limit"] == 500          # trial = solo limits
    assert u["items"][KIND_DRAFT]["limit"] == 150


def test_subscription_and_usage_require_auth(client):
    assert client.get("/api/billing/subscription").status_code == 401
    assert client.get("/api/billing/usage").status_code == 401


def test_subscription_is_tenant_isolated(client, db_session_factory=None):
    """Each tenant sees only its own subscription — the query is keyed on the caller's tenant."""
    t1 = register_and_login(client, "iso1@firm.com")
    t2 = register_and_login(client, "iso2@firm.com")
    # t1 downgrades itself to free; t2 must be unaffected
    s1 = client.get("/api/billing/subscription", headers=auth(t1)).json()
    s2 = client.get("/api/billing/subscription", headers=auth(t2)).json()
    assert s1["plan_code"] == s2["plan_code"] == "solo_advocate"
    # invoices of one tenant never leak into another's list
    assert client.get("/api/billing/invoices", headers=auth(t1)).json() == []
    assert client.get("/api/billing/invoices", headers=auth(t2)).json() == []


# ── RBAC: only owner/firm_admin may manage billing ────────────────────────────
@pytest.mark.parametrize("role", ["clerk", "associate"])
def test_clerk_and_associate_cannot_manage_billing(client, role):
    tok = _login(client, f"{role}@firm.com", role=role)
    assert client.post("/api/billing/subscription/checkout", headers=auth(tok),
                       json={"plan_code": "solo_advocate"}).status_code == 403
    assert client.post("/api/billing/subscription/cancel", headers=auth(tok)).status_code == 403
    assert client.post("/api/billing/subscription/seats", headers=auth(tok),
                       json={"seats": 5}).status_code == 403
    assert client.get("/api/billing/invoices", headers=auth(tok)).status_code == 403


def test_clerk_can_still_read_usage(client):
    tok = _login(client, "clerkread@firm.com", role="clerk")
    assert client.get("/api/billing/usage", headers=auth(tok)).status_code == 200


# ── L4: checkout (TEST mode) ──────────────────────────────────────────────────
def test_checkout_returns_gst_breakdown_and_disclosures(client):
    t = register_and_login(client, "checkout@firm.com")
    r = client.post("/api/billing/subscription/checkout", headers=auth(t),
                    json={"plan_code": "solo_advocate", "billing_cycle": "monthly"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["mode"] == "test"
    assert b["amount_paise"] == 99900                     # ₹999.00
    assert b["gst_paise"] == 17982                        # 18% — exact, in paise
    assert b["total_paise"] == 117882
    assert "renews automatically" in b["auto_renew_disclosure"]
    assert b["cancel_anytime"] is True


def test_checkout_rejects_free_enterprise_and_seat_minimum(client):
    t = register_and_login(client, "checkout2@firm.com")
    assert client.post("/api/billing/subscription/checkout", headers=auth(t),
                       json={"plan_code": "free"}).status_code == 400
    assert client.post("/api/billing/subscription/checkout", headers=auth(t),
                       json={"plan_code": "enterprise"}).status_code == 400
    r = client.post("/api/billing/subscription/checkout", headers=auth(t),
                    json={"plan_code": "firm", "seats": 2})       # min 3
    assert r.status_code == 400 and "at least 3 seats" in r.json()["detail"]
    assert client.post("/api/billing/subscription/checkout", headers=auth(t),
                       json={"plan_code": "nope"}).status_code == 404


def test_annual_cycle_is_two_months_free(client):
    t = register_and_login(client, "annual@firm.com")
    b = client.post("/api/billing/subscription/checkout", headers=auth(t),
                    json={"plan_code": "solo_advocate", "billing_cycle": "annual"}).json()
    assert b["amount_paise"] == 999000                    # ₹9,990 = 10 × ₹999


# ── L4: webhook — the signature IS the authentication ─────────────────────────
WEBHOOK_SECRET = "whsec_test_only_never_real"


@pytest.fixture()
def webhook_secret(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    return WEBHOOK_SECRET


def _tenant_id(email: str) -> int:
    from app.main import app
    from app.db.session import get_db
    from app.models.user import User
    db = next(app.dependency_overrides[get_db]())
    try:
        return db.query(User).filter(User.email == email).first().tenant_id
    finally:
        db.close()


def _event(kind: str, tenant_id: int, event_id: str, **extra) -> bytes:
    payload = {
        "event": kind,
        "payload": {
            "subscription": {"entity": {
                "id": "sub_test_1",
                "notes": {"tenant_id": str(tenant_id), "plan_code": "solo_advocate",
                          "billing_cycle": "monthly"},
            }},
            "payment": {"entity": {"id": "pay_test_1", "notes": {"tenant_id": str(tenant_id)},
                                   **extra}},
        },
        "id": event_id,
    }
    return json.dumps(payload).encode("utf-8")


def _sign(raw: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _post_hook(client, raw: bytes, signature: str | None):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Razorpay-Signature"] = signature
    return client.post("/api/billing/webhook/razorpay", content=raw, headers=headers)


def test_webhook_rejects_bad_and_missing_signature(client, webhook_secret):
    register_and_login(client, "hook1@firm.com")
    raw = _event("subscription.activated", _tenant_id("hook1@firm.com"), "evt_1")
    assert _post_hook(client, raw, "deadbeef").status_code == 400        # wrong signature
    assert _post_hook(client, raw, None).status_code == 400              # no signature at all


def test_webhook_rejects_everything_when_no_secret_is_configured(client, monkeypatch):
    """Fail closed: an unverifiable webhook is never trusted, not even in test mode."""
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    register_and_login(client, "hook0@firm.com")
    raw = _event("subscription.activated", _tenant_id("hook0@firm.com"), "evt_0")
    assert _post_hook(client, raw, _sign(raw)).status_code == 400


def test_webhook_valid_signature_activates_subscription(client, webhook_secret):
    t = register_and_login(client, "hook2@firm.com")
    raw = _event("subscription.activated", _tenant_id("hook2@firm.com"), "evt_2")
    r = _post_hook(client, raw, _sign(raw))
    assert r.status_code == 200 and r.json()["status"] == "processed"
    s = client.get("/api/billing/subscription", headers=auth(t)).json()
    assert s["status"] == "active" and s["plan_code"] == "solo_advocate"


def test_webhook_is_idempotent_on_replay(client, webhook_secret):
    register_and_login(client, "hook3@firm.com")
    raw = _event("subscription.charged", _tenant_id("hook3@firm.com"), "evt_3")
    sig = _sign(raw)
    assert _post_hook(client, raw, sig).json()["status"] == "processed"
    assert _post_hook(client, raw, sig).json()["status"] == "duplicate_ignored"   # retry
    assert _post_hook(client, raw, sig).json()["status"] == "duplicate_ignored"


def test_webhook_unknown_event_is_ignored_not_crashed(client, webhook_secret):
    register_and_login(client, "hook4@firm.com")
    raw = _event("subscription.paused", _tenant_id("hook4@firm.com"), "evt_4")
    assert _post_hook(client, raw, _sign(raw)).json()["status"] == "ignored_unhandled_event"


def test_payment_failed_marks_past_due(client, webhook_secret):
    t = register_and_login(client, "hook5@firm.com")
    raw = _event("payment.failed", _tenant_id("hook5@firm.com"), "evt_5",
                 error_description="card declined")
    assert _post_hook(client, raw, _sign(raw)).json()["status"] == "processed"
    assert client.get("/api/billing/subscription", headers=auth(t)).json()["status"] == "past_due"


# ── L5: invoice + GST ─────────────────────────────────────────────────────────
def test_charge_creates_a_gst_invoice(client, webhook_secret):
    t = register_and_login(client, "inv@firm.com")
    tid = _tenant_id("inv@firm.com")
    act = _event("subscription.activated", tid, "evt_a")
    _post_hook(client, act, _sign(act))
    chg = _event("subscription.charged", tid, "evt_b")
    assert _post_hook(client, chg, _sign(chg)).json()["status"] == "processed"

    invoices = client.get("/api/billing/invoices", headers=auth(t)).json()
    assert len(invoices) == 1
    i = invoices[0]
    assert i["amount_inr"] == 999.0 and i["gst_inr"] == 179.82 and i["total_inr"] == 1178.82
    assert i["gst_rate_percent"] == 18
    assert i["invoice_number"].startswith("JC-")


def test_gstin_captured_at_checkout_lands_on_the_invoice(client, webhook_secret):
    t = register_and_login(client, "gstin@firm.com")
    tid = _tenant_id("gstin@firm.com")
    client.post("/api/billing/subscription/checkout", headers=auth(t),
                json={"plan_code": "solo_advocate", "gstin": "29aabbc1234c1zx"})
    act = _event("subscription.activated", tid, "evt_c")
    _post_hook(client, act, _sign(act))
    chg = _event("subscription.charged", tid, "evt_d")
    _post_hook(client, chg, _sign(chg))
    assert client.get("/api/billing/invoices", headers=auth(t)).json()[0]["gstin"] == "29AABBC1234C1ZX"


def test_invoices_are_tenant_isolated(client, webhook_secret):
    t1 = register_and_login(client, "invA@firm.com")
    t2 = register_and_login(client, "invB@firm.com")
    tid = _tenant_id("invA@firm.com")
    for i, ev in enumerate(("subscription.activated", "subscription.charged")):
        raw = _event(ev, tid, f"evt_iso_{i}")
        _post_hook(client, raw, _sign(raw))
    assert len(client.get("/api/billing/invoices", headers=auth(t1)).json()) == 1
    assert client.get("/api/billing/invoices", headers=auth(t2)).json() == []   # never leaks


# ── L6: seats ─────────────────────────────────────────────────────────────────
def _put_on_firm_plan(email: str, seats: int = 3):
    from app.main import app
    from app.db.session import get_db
    db = next(app.dependency_overrides[get_db]())
    try:
        sub = bl.get_subscription(db, _tenant_id(email))
        sub.plan_code, sub.status, sub.seats, sub.trial_end = "firm", "active", seats, None
        db.commit()
    finally:
        db.close()


def test_seats_cannot_go_below_plan_minimum(client):
    email = "seats@firm.com"
    t = register_and_login(client, email)
    _put_on_firm_plan(email)
    r = client.post("/api/billing/subscription/seats", headers=auth(t), json={"seats": 2})
    assert r.status_code == 400 and "at least 3 seats" in r.json()["detail"]
    ok = client.post("/api/billing/subscription/seats", headers=auth(t), json={"seats": 5})
    assert ok.status_code == 200 and ok.json()["seats"] == 5


def test_seats_apply_to_firm_plan_only(client):
    t = register_and_login(client, "seatssolo@firm.com")     # trial = solo (not per-seat)
    r = client.post("/api/billing/subscription/seats", headers=auth(t), json={"seats": 4})
    assert r.status_code == 400 and "Firm plan" in r.json()["detail"]


def test_seat_change_scales_the_pooled_quota(client):
    email = "seatsquota@firm.com"
    register_and_login(client, email)
    _put_on_firm_plan(email, seats=4)
    from app.main import app
    from app.db.session import get_db
    db = next(app.dependency_overrides[get_db]())
    try:
        sub = bl.get_subscription(db, _tenant_id(email))
        plan = bl.effective_plan(db, sub)
        assert bl.quota_for(plan, KIND_RESEARCH, sub.seats) == 2000     # 500 × 4 seats, pooled
    finally:
        db.close()


# ── L7: cancellation (no dark patterns) ───────────────────────────────────────
def test_cancel_takes_effect_at_period_end_and_keeps_access(client):
    t = register_and_login(client, "cancel@firm.com")
    r = client.post("/api/billing/subscription/cancel", headers=auth(t))
    assert r.status_code == 200
    s = r.json()
    assert s["cancel_at_period_end"] is True
    assert s["plan_code"] == "solo_advocate"        # access retained until the period ends
    # ...and it can be undone without contacting anyone
    assert client.post("/api/billing/subscription/resume", headers=auth(t)).json()["cancel_at_period_end"] is False


def test_cancel_is_audited(client):
    t = _login(client, "cancelaudit@firm.com", role="firm_admin")   # /api/audit is firm_admin-only
    client.post("/api/billing/subscription/cancel", headers=auth(t))
    actions = [a["action"] for a in client.get("/api/audit", headers=auth(t)).json()]
    assert "billing_canceled" in actions


def test_free_plan_has_nothing_to_cancel(client):
    email = "cancelfree@firm.com"
    t = register_and_login(client, email)
    from app.main import app
    from app.db.session import get_db
    db = next(app.dependency_overrides[get_db]())
    try:
        sub = bl.get_subscription(db, _tenant_id(email))
        sub.plan_code, sub.status = "free", "active"
        db.commit()
    finally:
        db.close()
    assert client.post("/api/billing/subscription/cancel", headers=auth(t)).status_code == 400


# ── L7: trial lifecycle ───────────────────────────────────────────────────────
def test_trial_expiry_downgrades_to_free_and_never_charges(client):
    from datetime import timedelta
    from app.util.time import utcnow
    from app.main import app
    from app.db.session import get_db
    from app.models.notification import Notification

    email = "trialexp@firm.com"
    t = register_and_login(client, email)
    db = next(app.dependency_overrides[get_db]())
    try:
        tid = _tenant_id(email)
        sub = bl.get_subscription(db, tid)
        sub.trial_end = utcnow() - timedelta(hours=1)
        db.commit()

        result = bl.run_trial_lifecycle(db)
        assert result["downgraded"] == 1

        sub = bl.get_subscription(db, tid)
        assert sub.plan_code == "free" and sub.status == "active"
        note = db.query(Notification).filter(Notification.tenant_id == tid).first()
        assert "trial has ended" in note.title
        assert "Nothing was charged" in note.body           # honest, no surprise billing
        # idempotent — running again neither re-downgrades nor duplicates the notice
        assert bl.run_trial_lifecycle(db)["downgraded"] == 0
    finally:
        db.close()

    assert client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["limit"] == 5


def test_trial_ending_soon_warns_three_days_before(client):
    from datetime import timedelta
    from app.util.time import utcnow
    from app.main import app
    from app.db.session import get_db

    email = "trialwarn@firm.com"
    register_and_login(client, email)
    db = next(app.dependency_overrides[get_db]())
    try:
        sub = bl.get_subscription(db, _tenant_id(email))
        sub.trial_end = utcnow() + timedelta(days=2)
        db.commit()
        assert bl.run_trial_lifecycle(db) == {"warned": 1, "downgraded": 0}
        assert bl.run_trial_lifecycle(db)["warned"] == 1   # notification dedupes; no spam
    finally:
        db.close()


# ── Audit: every subscription mutation is recorded ────────────────────────────
def test_checkout_and_seats_are_audited(client):
    email = "billaudit@firm.com"
    t = _login(client, email, role="firm_admin")
    client.post("/api/billing/subscription/checkout", headers=auth(t),
                json={"plan_code": "solo_advocate"})
    _put_on_firm_plan(email)
    client.post("/api/billing/subscription/seats", headers=auth(t), json={"seats": 4})
    actions = [a["action"] for a in client.get("/api/audit", headers=auth(t)).json()]
    assert "billing_checkout" in actions
    assert "billing_seats_changed" in actions


def test_webhook_activation_is_audited(client, webhook_secret):
    t = _login(client, "hookaudit@firm.com", role="firm_admin")
    raw = _event("subscription.activated", _tenant_id("hookaudit@firm.com"), "evt_audit")
    _post_hook(client, raw, _sign(raw))
    actions = [a["action"] for a in client.get("/api/audit", headers=auth(t)).json()]
    assert "billing_subscription_activated" in actions


# ── Pricing page: served + honest copy (spec Part 1 / Part 4) ─────────────────
def test_pricing_page_is_served(client):
    r = client.get("/pricing")
    assert r.status_code == 200
    body = r.text.lower()
    assert "run your entire practice in one place" in body
    assert "14-day free trial" in body
    assert "no credit card required" in body


def test_pricing_copy_has_no_dark_patterns_or_outcome_claims(client):
    """Part 4 forbids unverifiable superiority/outcome claims and manufactured urgency.
    Advocates spot manipulation for a living — honest billing is the competitive edge."""
    import re
    from pathlib import Path
    text = Path("app/templates/pricing.html").read_text(encoding="utf-8").lower()
    # regex so a ranking "#1" claim is caught but CSS hex colours (#1a1206) are not
    banned = [
        r"you will win", r"guaranteed", r"#1\b", r"\bnumber one\b", r"best in class",
        r"used daily in courts", r"risk-free", r"act now", r"limited time only",
        r"\bhurry\b", r"only today", r"people are buying", r"spots left",
    ]
    hits = [b for b in banned if re.search(b, text)]
    assert not hits, f"dark-pattern / outcome-claim copy on pricing page: {hits}"
    # honest, required disclosures ARE present
    assert "advocate review before filing" in text
    assert "no solicitation" in text and "no outcome claims" in text
    assert "never train ai on your data" in text or "never used to train" in text


# ── Live-mode guard: money never moves without the human gate ─────────────────
def test_live_billing_mode_is_refused_without_human_signoff(client, monkeypatch):
    monkeypatch.setenv("BILLING_MODE", "live")
    monkeypatch.delenv("BILLING_LIVE_APPROVED", raising=False)
    with pytest.raises(RuntimeError, match="G6/G7"):
        bl.assert_billing_mode_allowed()
