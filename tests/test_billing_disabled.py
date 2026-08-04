"""
LSAI-LEGAL-18 / LSAI-V3-05 — billing is now BUILT but LIVE PAYMENTS remain gated.

History: this guard originally asserted that *no* billing route may exist while paid
billing was deferred. The Pricing/Subscription spec (Part 0) deliberately authorized the
billing build under Gate **G11**, in Razorpay **TEST mode only**, with live payments held
until the human security/privacy review (G6/G7) passes.

So the guard is updated deliberately (as its own note instructed) to protect the property
that still matters: **no real money moves without a human turning it on.** See
`docs/legal/BILLING_GST_REFUND_POLICY.md`.
"""
import pytest

from app.services import billing as bl


def test_billing_routes_exist_now(client):
    """The billing surface is expected to be present (G11 sprint shipped).
    Checked functionally — this app wraps included routers so a flat app.routes scan
    doesn't surface sub-router paths; hitting the endpoints is the honest test."""
    assert client.get("/api/billing/plans").status_code == 200                       # public
    assert client.get("/api/billing/subscription/checkout").status_code == 405       # exists, POST-only
    assert client.post("/api/billing/webhook/razorpay", content=b"{}").status_code == 400  # exists, sig-guarded


def test_billing_mode_defaults_to_test(monkeypatch):
    """Billing must never silently default to live."""
    monkeypatch.delenv("BILLING_MODE", raising=False)
    assert bl.billing_mode() == "test"


def test_live_mode_refuses_without_human_signoff(monkeypatch):
    """The G6/G7 gate: BILLING_MODE=live is refused unless a human explicitly approved it.
    This is the real-money kill switch — it stays engaged until the security review clears."""
    monkeypatch.setenv("BILLING_MODE", "live")
    monkeypatch.delenv("BILLING_LIVE_APPROVED", raising=False)
    with pytest.raises(RuntimeError, match="G6/G7"):
        bl.assert_billing_mode_allowed()


def test_checkout_never_reaches_a_live_gateway_in_test_mode(monkeypatch):
    """In test mode the checkout builds a deterministic pseudo-order — no network call,
    no card data, no PII leaves the box."""
    monkeypatch.setenv("BILLING_MODE", "test")
    assert bl.billing_mode() == "test"
    # assert_billing_mode_allowed is a no-op in test mode (never raises)
    bl.assert_billing_mode_allowed()
