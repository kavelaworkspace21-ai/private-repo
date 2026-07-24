"""
Razorpay webhook handling — signature-verified and idempotent (spec 3.3).

Trust model: a webhook carries no authentication. The ONLY thing that makes its
contents believable is the HMAC-SHA256 signature over the raw body. So:
  • No secret configured  → reject (fail closed). We never "trust in test mode".
  • Signature mismatch    → reject before parsing a single field.
  • Replayed event id     → recorded once, then ignored (Razorpay retries at-least-once).

We store only Razorpay identifiers and billing metadata. Card data never touches us.
"""
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta

from app.util.time import utcnow

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing import (
    Invoice, Subscription, WebhookEvent,
    STATUS_ACTIVE, STATUS_PAST_DUE, CYCLE_ANNUAL, CYCLE_MONTHLY,
)
from app.services import billing as bl
from app.services.tenancy import write_audit

logger = logging.getLogger(__name__)

SYSTEM_ACTOR = 0   # webhooks are not a human action; audit rows record the system actor

HANDLED_EVENTS = {
    "subscription.activated",
    "subscription.charged",
    "subscription.halted",
    "payment.failed",
}


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    """HMAC-SHA256(raw_body, RAZORPAY_WEBHOOK_SECRET) == X-Razorpay-Signature."""
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET") or ""
    if not secret or not signature:
        return False                       # fail closed — unverifiable means untrusted
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _entity(event: dict, key: str) -> dict:
    return ((event.get("payload") or {}).get(key) or {}).get("entity") or {}


def _resolve_tenant(db: Session, event: dict) -> tuple[int | None, Subscription | None]:
    """Tenant comes from Razorpay `notes` (we set them at checkout) or from the
    subscription id we already stored. Never from an unauthenticated guess."""
    sub_e, pay_e = _entity(event, "subscription"), _entity(event, "payment")
    for e in (sub_e, pay_e):
        notes = e.get("notes") or {}
        raw = notes.get("tenant_id")
        if raw is not None:
            try:
                tid = int(raw)
            except (TypeError, ValueError):
                continue
            return tid, bl.get_subscription(db, tid)
    rzp_sub_id = sub_e.get("id")
    if rzp_sub_id:
        sub = db.query(Subscription).filter(
            Subscription.razorpay_subscription_id == rzp_sub_id).first()
        if sub:
            return sub.tenant_id, sub
    return None, None


def _period_end(start: datetime, cycle: str) -> datetime:
    return start + timedelta(days=365 if cycle == CYCLE_ANNUAL else 30)


def _create_invoice(db: Session, sub: Subscription, payment_id: str | None) -> Invoice | None:
    """GST breakdown is computed from the plan (authoritative), not from the gateway blob."""
    plan = bl.get_plan(db, sub.plan_code)
    if not plan or plan.price_monthly_inr is None:
        return None
    try:
        taxable = bl.price_paise(plan, sub.billing_cycle, sub.seats, sub.founding_member)
    except ValueError:
        return None
    amount, gst, total = bl.compute_gst(taxable)
    inv = Invoice(
        tenant_id=sub.tenant_id, subscription_id=sub.id,
        amount_paise=amount, gst_paise=gst, total_paise=total,
        gst_rate_percent=bl.gst_rate_percent(), gstin=sub.gstin,
        invoice_number=bl.next_invoice_number(db),
        period_start=sub.current_period_start, period_end=sub.current_period_end,
        razorpay_payment_id=payment_id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def handle_event(db: Session, event: dict, header_event_id: str | None = None) -> str:
    """Returns a short status string. Assumes the signature is ALREADY verified."""
    event_type = (event.get("event") or "").strip()
    pay_e = _entity(event, "payment")
    sub_e = _entity(event, "subscription")

    event_id = (header_event_id or event.get("id")
                or pay_e.get("id") or sub_e.get("id"))
    if not event_id:
        return "ignored_no_event_id"

    # ── Idempotency ledger: claim the event id first; a replay loses the race. ──
    ledger = WebhookEvent(event_id=str(event_id), event_type=event_type or "unknown")
    db.add(ledger)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return "duplicate_ignored"

    if event_type not in HANDLED_EVENTS:
        return "ignored_unhandled_event"

    tenant_id, sub = _resolve_tenant(db, event)
    if not sub:
        logger.warning("Razorpay webhook %s: no subscription resolved", event_type)
        return "ignored_unknown_subscription"

    ledger.tenant_id = tenant_id
    db.commit()

    now = utcnow()
    action, detail = None, None

    if event_type == "subscription.activated":
        notes = sub_e.get("notes") or {}
        if notes.get("plan_code") and bl.get_plan(db, notes["plan_code"]):
            sub.plan_code = notes["plan_code"]
        if notes.get("billing_cycle") in (CYCLE_MONTHLY, CYCLE_ANNUAL):
            sub.billing_cycle = notes["billing_cycle"]
        if sub_e.get("id"):
            sub.razorpay_subscription_id = sub_e["id"]
        sub.status = STATUS_ACTIVE
        sub.trial_end = None
        sub.current_period_start = now
        sub.current_period_end = _period_end(now, sub.billing_cycle)
        db.commit()
        action, detail = "billing_subscription_activated", f"plan={sub.plan_code}"

    elif event_type == "subscription.charged":
        sub.status = STATUS_ACTIVE
        # A charge opens the next period.
        sub.current_period_start = now
        sub.current_period_end = _period_end(now, sub.billing_cycle)
        db.commit()
        inv = _create_invoice(db, sub, pay_e.get("id"))
        action = "billing_subscription_charged"
        detail = f"invoice={inv.invoice_number}" if inv else "invoice=skipped(no self-serve price)"

    elif event_type == "subscription.halted":
        sub.status = STATUS_PAST_DUE
        db.commit()
        action, detail = "billing_subscription_halted", "payment retries exhausted"

    elif event_type == "payment.failed":
        sub.status = STATUS_PAST_DUE
        db.commit()
        action, detail = "billing_payment_failed", pay_e.get("error_description") or "payment failed"

    if action:
        write_audit(db, tenant_id=sub.tenant_id, user_id=SYSTEM_ACTOR,
                    action=action, entity="Subscription", entity_id=sub.id, detail=detail)
    return "processed"
