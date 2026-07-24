"""
Billing & subscriptions (LSAI-V3-05 · Gate G11 · Phase C).

Doctrine:
  • Only the firm owner (advocate) or firm_admin may manage a subscription.
    clerk / associate are refused (RBAC).
  • Every subscription mutation writes an AuditLog row.
  • Tenant isolation: a subscription, its usage and its invoices are visible only
    to that tenant. Cross-tenant reads are structurally impossible here — every
    query is keyed on the caller's own tenant_id.
  • No dark patterns: cancellation is one authenticated POST that takes effect at
    period end, auto-renew is disclosed at checkout, no card is required for a trial.
  • BILLING_MODE=test until G6/G7 human review passes.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.billing import (
    Invoice, Subscription, STATUS_CANCELED, STATUS_EXPIRED, CYCLE_ANNUAL,
)
from app.auth.dependencies import get_current_user, require_role
from app.services import billing as bl
from app.services.tenancy import current_tenant_id, write_audit
from app.schemas.billing import (
    PlanOut, PricingOut, SubscriptionOut, UsageOut, CheckoutRequest, CheckoutOut,
    SeatsRequest, InvoiceOut,
)

router = APIRouter()

# The firm owner (a practising advocate running their own tenant) or the firm_admin.
# clerk / associate must never reach a billing mutation.
require_billing_admin = require_role(UserRole.advocate, UserRole.firm_admin)

AUTO_RENEW_DISCLOSURE = (
    "This subscription renews automatically at the end of each billing period. "
    "We email you before every renewal. You can cancel anytime from Account → Billing; "
    "your plan then stays active until the end of the period you have already paid for."
)
REFUND_POLICY = (
    "Annual plans are refundable pro-rata within the first 14 days. "
    "Monthly plans are not refunded mid-period, but cancelling stops the next charge."
)


# ── Public pricing page data ──────────────────────────────────────────────────
@router.get("/plans", response_model=PricingOut)
def list_plans(db: Session = Depends(get_db)):
    """Public — the pricing page reads its numbers from here, never from hard-coded copy."""
    plans = bl.list_active_plans(db)
    return PricingOut(
        plans=[PlanOut.model_validate(p) for p in plans],
        founding_member=bl.FOUNDING_MEMBER,
        trial=bl.TRIAL,
        gst=bl.gst_config(),
        billing_mode=bl.billing_mode(),
    )


# ── Current subscription + usage (any member of the tenant) ───────────────────
def _sub_out(db: Session, sub: Subscription) -> SubscriptionOut:
    plan = bl.effective_plan(db, sub)
    return SubscriptionOut(
        plan_code=plan.code, plan_name=plan.name, status=sub.status,
        billing_cycle=sub.billing_cycle, seats=sub.seats,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end, trial_end=sub.trial_end,
        cancel_at_period_end=sub.cancel_at_period_end,
        founding_member=sub.founding_member, gstin=sub.gstin,
    )


@router.get("/subscription", response_model=SubscriptionOut)
def my_subscription(db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    return _sub_out(db, bl.get_or_create_subscription(db, tenant_id))


@router.get("/usage", response_model=UsageOut)
def my_usage(db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    return UsageOut(**bl.usage_snapshot(db, tenant_id))


# ── Checkout (Razorpay TEST mode) ─────────────────────────────────────────────
@router.post("/subscription/checkout", response_model=CheckoutOut)
def checkout(body: CheckoutRequest, db: Session = Depends(get_db),
             user: User = Depends(require_billing_admin)):
    bl.assert_billing_mode_allowed()          # refuses live money without G6/G7 sign-off

    plan = bl.get_plan(db, body.plan_code)
    if not plan or not plan.active:
        raise HTTPException(404, "Unknown plan.")
    if plan.billing == "none":
        raise HTTPException(400, "The Free plan needs no checkout.")
    if plan.billing == "manual_invoice":
        raise HTTPException(400, "Enterprise is sales-led — please contact sales.")
    if plan.per_seat and plan.min_seats and body.seats < plan.min_seats:
        raise HTTPException(400, f"The {plan.name} plan requires at least {plan.min_seats} seats.")

    sub = bl.get_or_create_subscription(db, user.tenant_id)
    amount, gst, total = bl.compute_gst(
        bl.price_paise(plan, body.billing_cycle, body.seats, sub.founding_member))

    order_id = None
    key_id = None
    if bl.billing_mode() == "live":
        # Real order creation happens only after G6/G7. Guarded above; kept explicit here.
        raise HTTPException(503, "Live billing is not enabled. Awaiting security review sign-off.")
    else:
        import os
        key_id = os.getenv("RAZORPAY_KEY_ID") or None
        # Deterministic pseudo-order for TEST mode: no network call, no card data, no PII.
        order_id = f"order_test_{user.tenant_id}_{plan.code}_{body.billing_cycle}_{body.seats}"

    if body.gstin:
        sub.gstin = body.gstin.strip().upper()   # DPDP: billing PII, covered by ConsentRecord
        db.commit()

    write_audit(db, tenant_id=user.tenant_id, user_id=user.id, action="billing_checkout",
                entity="Subscription", entity_id=sub.id,
                detail=f"{plan.code}/{body.billing_cycle}/seats={body.seats}/mode={bl.billing_mode()}")

    return CheckoutOut(
        provider="razorpay", mode=bl.billing_mode(), key_id=key_id, order_id=order_id,
        amount_paise=amount, gst_paise=gst, total_paise=total,
        plan_code=plan.code, billing_cycle=body.billing_cycle, seats=body.seats,
        auto_renew_disclosure=AUTO_RENEW_DISCLOSURE, refund_policy=REFUND_POLICY,
    )


# ── Seats (firm plan) ─────────────────────────────────────────────────────────
@router.post("/subscription/seats", response_model=SubscriptionOut)
def change_seats(body: SeatsRequest, db: Session = Depends(get_db),
                 user: User = Depends(require_billing_admin)):
    sub = bl.get_or_create_subscription(db, user.tenant_id)
    plan = bl.get_plan(db, sub.plan_code)
    if not plan or not plan.per_seat:
        raise HTTPException(400, "Seats apply to the Firm plan only.")
    if plan.min_seats and body.seats < plan.min_seats:
        raise HTTPException(400, f"The {plan.name} plan requires at least {plan.min_seats} seats.")

    # Never strand a live member without a seat.
    members = db.query(User).filter(User.tenant_id == user.tenant_id,
                                    User.is_active.is_(True)).count()
    if body.seats < members:
        raise HTTPException(400, f"Your firm has {members} active members — buy at least {members} seats "
                                 f"or deactivate members first.")

    before = sub.seats
    sub.seats = body.seats
    db.commit(); db.refresh(sub)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id, action="billing_seats_changed",
                entity="Subscription", entity_id=sub.id, detail=f"{before} -> {body.seats}")
    return _sub_out(db, sub)


# ── Cancellation (two clicks, effective at period end) ────────────────────────
@router.post("/subscription/cancel", response_model=SubscriptionOut)
def cancel(db: Session = Depends(get_db), user: User = Depends(require_billing_admin)):
    sub = bl.get_or_create_subscription(db, user.tenant_id)
    if sub.plan_code == bl.FREE:
        raise HTTPException(400, "You are on the Free plan — there is nothing to cancel.")
    from app.util.time import utcnow
    sub.cancel_at_period_end = True
    sub.canceled_at = utcnow()
    db.commit(); db.refresh(sub)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id, action="billing_canceled",
                entity="Subscription", entity_id=sub.id,
                detail=f"effective {sub.current_period_end:%Y-%m-%d} (access retained until then)")
    return _sub_out(db, sub)


@router.post("/subscription/resume", response_model=SubscriptionOut)
def resume(db: Session = Depends(get_db), user: User = Depends(require_billing_admin)):
    """Undo a scheduled cancellation before the period ends."""
    sub = bl.get_or_create_subscription(db, user.tenant_id)
    if not sub.cancel_at_period_end:
        raise HTTPException(400, "This subscription is not scheduled to cancel.")
    sub.cancel_at_period_end = False
    sub.canceled_at = None
    db.commit(); db.refresh(sub)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id, action="billing_resumed",
                entity="Subscription", entity_id=sub.id)
    return _sub_out(db, sub)


# ── Invoices (tenant-scoped) ──────────────────────────────────────────────────
@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(db: Session = Depends(get_db), user: User = Depends(require_billing_admin)):
    rows = (db.query(Invoice)
              .filter(Invoice.tenant_id == user.tenant_id)
              .order_by(Invoice.id.desc()).all())
    return [InvoiceOut(
        id=i.id, invoice_number=i.invoice_number,
        amount_inr=i.amount_paise / 100, gst_inr=i.gst_paise / 100, total_inr=i.total_paise / 100,
        gst_rate_percent=i.gst_rate_percent, gstin=i.gstin,
        period_start=i.period_start, period_end=i.period_end, created_at=i.created_at,
    ) for i in rows]


# ── Razorpay webhook (signature-verified, idempotent) ─────────────────────────
@router.post("/webhook/razorpay", status_code=status.HTTP_200_OK)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Unauthenticated by design — trust comes from the HMAC signature, nothing else.
    An unverified webhook is rejected before a single byte of it is believed."""
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")
    from app.services.razorpay_webhook import verify_signature, handle_event
    if not verify_signature(raw, signature):
        raise HTTPException(400, "Invalid webhook signature.")
    import json
    try:
        event = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Malformed webhook body.")
    result = handle_event(db, event, request.headers.get("X-Razorpay-Event-Id"))
    return {"status": result}
