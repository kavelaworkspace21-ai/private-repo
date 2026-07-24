"""
Billing domain (LSAI-V3-05 · Gate G11 · Phase C).

Doctrine notes:
  • Prices and limits live HERE as data (SubscriptionPlan rows). Business logic must read
    `plan.limits`, never hard-code a number. Re-pricing = a data change, not a code change.
  • Subscription / UsageEvent / Invoice all carry `tenant_id` (CLAUDE.md §5).
    SubscriptionPlan is a GLOBAL catalogue (no tenant_id) — it is not a business row.
  • Money is stored as INTEGER PAISE. Float rupees cannot represent 18% GST on ₹999 exactly.
    The API surfaces rupees; the database never rounds.
  • Every subscription mutation writes an AuditLog row (done in the router/service).
  • BILLING_MODE stays "test" until G6/G7 pass and a human approves (Part 0 of the spec).
"""
from app.util.time import utcnow

from sqlalchemy import String, Integer, Boolean, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


# ── Statuses / kinds (single source of truth) ─────────────────────────────────
STATUS_TRIALING = "trialing"
STATUS_ACTIVE = "active"
STATUS_PAST_DUE = "past_due"
STATUS_CANCELED = "canceled"
STATUS_EXPIRED = "expired"

CYCLE_MONTHLY = "monthly"
CYCLE_ANNUAL = "annual"

KIND_RESEARCH = "research_query"
KIND_DRAFT = "draft"


class SubscriptionPlan(Base):
    """The pricing catalogue. Global (not tenant-scoped) — seeded, then editable as data."""
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    # Whole rupees; None = custom / sales-led (enterprise).
    price_monthly_inr: Mapped[int | None] = mapped_column(Integer)
    price_annual_inr: Mapped[int | None] = mapped_column(Integer)

    billing: Mapped[str] = mapped_column(String(20), default="none", nullable=False)  # none|razorpay|manual_invoice
    per_seat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_seats: Mapped[int | None] = mapped_column(Integer)
    trial_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    limits: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Subscription(Base):
    """One live subscription per tenant."""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, unique=True, nullable=False)

    plan_code: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_TRIALING, nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(10), default=CYCLE_MONTHLY, nullable=False)
    seats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    current_period_start: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    current_period_end: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    trial_end: Mapped[DateTime | None] = mapped_column(DateTime)

    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(80), index=True)
    razorpay_customer_id: Mapped[str | None] = mapped_column(String(80))
    founding_member: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # No dark patterns: cancellation always takes effect at period end, never mid-period.
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[DateTime | None] = mapped_column(DateTime)

    gstin: Mapped[str | None] = mapped_column(String(20))   # DPDP: billing PII

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UsageEvent(Base):
    """One metered AI action. Counted per billing period to enforce fair-use limits.

    `created_at` is stamped PYTHON-side (not `func.now()`) on purpose: the period window
    (`Subscription.current_period_start`) is a Python `utcnow()` with microseconds, but
    SQLite's CURRENT_TIMESTAMP truncates to whole seconds. A DB-side default therefore
    lands *before* the period start for any usage recorded in the same second as signup,
    and the row silently drops out of the count. One clock, one precision, on both sides.
    """
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), index=True, nullable=False)  # research_query|draft
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=utcnow, index=True)


class Invoice(Base):
    """A GST invoice for a successful charge. Amounts in PAISE (integers)."""
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    subscription_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)   # taxable value
    gst_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    gst_rate_percent: Mapped[int] = mapped_column(Integer, default=18, nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(20))                # customer GSTIN (input credit)

    invoice_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    period_start: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[DateTime] = mapped_column(DateTime, nullable=False)

    razorpay_payment_id: Mapped[str | None] = mapped_column(String(80), index=True)
    pdf_path: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class WebhookEvent(Base):
    """Processed Razorpay events — the idempotency ledger. A replayed event is a no-op."""
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
