"""
Billing service — plans, subscriptions, quotas, GST (LSAI-V3-05 · Gate G11).

The seed below is DATA, not logic. Every runtime decision reads a `SubscriptionPlan`
row from the database, so prices and fair-use limits can be tuned by real willingness-
to-pay from the closed beta without touching code (spec Part 0 / Part 4).

BILLING_MODE is "test" unless explicitly set. Live payments require G6/G7 + human
approval — `assert_billing_mode_allowed()` is the guard.
"""
import os
from datetime import datetime, timedelta

from app.util.time import utcnow

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.billing import (
    SubscriptionPlan, Subscription, UsageEvent,
    STATUS_TRIALING, STATUS_ACTIVE, STATUS_PAST_DUE, STATUS_CANCELED, STATUS_EXPIRED,
    CYCLE_MONTHLY, CYCLE_ANNUAL, KIND_RESEARCH, KIND_DRAFT,
)

FREE = "free"
SOLO = "solo_advocate"
FIRM = "firm"
ENTERPRISE = "enterprise"

# Plans that a subscription can be *entitled* to serve while unpaid.
LIVE_STATUSES = (STATUS_TRIALING, STATUS_ACTIVE, STATUS_PAST_DUE)


# ── SEED DATA (spec Part 2 — the launch hypothesis, tunable) ──────────────────
PLAN_SEED = [
    dict(code=FREE, name="Free", price_monthly_inr=0, price_annual_inr=0,
         billing="none", per_seat=False, min_seats=None, trial_days=0, sort_order=1,
         limits={
             "research_queries_per_month": 5,
             "drafts_per_month": 2,
             "court_diary": "read_only",
             "reminders": False,
             "vault_mb": 100,
             "rbac": False,
             "firm_audit_dashboard": False,
         }),
    dict(code=SOLO, name="Solo Advocate", price_monthly_inr=999, price_annual_inr=9990,
         billing="razorpay", per_seat=False, min_seats=None, trial_days=14, sort_order=2,
         limits={
             "research_queries_per_month": 500,
             "drafts_per_month": 150,
             "court_diary": "full",
             "reminders": True,
             "vault_mb": 5000,
             "rbac": False,
             "firm_audit_dashboard": False,
         }),
    dict(code=FIRM, name="Firm", price_monthly_inr=899, price_annual_inr=8990,
         billing="razorpay", per_seat=True, min_seats=3, trial_days=14, sort_order=3,
         limits={
             "research_queries_per_month": 500,     # per seat, pooled across the firm
             "drafts_per_month": 150,               # per seat, pooled across the firm
             "court_diary": "full",
             "reminders": True,
             "vault_mb_per_seat": 5000,
             "rbac": True,
             "firm_audit_dashboard": True,
         }),
    dict(code=ENTERPRISE, name="Enterprise", price_monthly_inr=None, price_annual_inr=None,
         billing="manual_invoice", per_seat=True, min_seats=None, trial_days=0, sort_order=4,
         limits={
             "research_queries_per_month": "custom",
             "drafts_per_month": "custom",
             "court_diary": "full",
             "reminders": True,
             "vault_mb_per_seat": "custom",
             "rbac": True,
             "firm_audit_dashboard": True,
             "sso": True,
         }),
]

FOUNDING_MEMBER = {
    "applies_to": SOLO,
    "price_monthly_inr": 499,
    "locked_for_life": True,
    "eligibility": "first closed-beta cohort only",
}

TRIAL = {
    "length_days": 14,
    "requires_card": False,          # never a dark pattern (spec Part 4)
    "applies_to": [SOLO, FIRM],
    "on_expiry": "downgrade to Free; notify 3 days before and on expiry",
}


# ── Config ────────────────────────────────────────────────────────────────────
def billing_mode() -> str:
    return (os.getenv("BILLING_MODE") or "test").strip().lower()


def gst_rate_percent() -> int:
    try:
        return int(os.getenv("GST_RATE_PERCENT") or 18)
    except ValueError:
        return 18


def gst_config() -> dict:
    return {"display": "exclusive", "rate_percent": gst_rate_percent(), "capture_gstin": True}


def assert_billing_mode_allowed() -> None:
    """Live payments are gated on the human security/privacy review (G6/G7).
    Until a human flips this on deliberately, we refuse to touch real money."""
    if billing_mode() == "live" and (os.getenv("BILLING_LIVE_APPROVED") or "").lower() not in ("1", "true", "yes"):
        raise RuntimeError(
            "BILLING_MODE=live requires BILLING_LIVE_APPROVED after G6/G7 human sign-off. "
            "Refusing to process real payments."
        )


# ── Plans (seeded, then read from the DB) ─────────────────────────────────────
def ensure_plans_seeded(db: Session) -> None:
    """Idempotent. Inserts any missing plan codes; never overwrites tuned prices."""
    existing = {c for (c,) in db.query(SubscriptionPlan.code).all()}
    added = False
    for row in PLAN_SEED:
        if row["code"] not in existing:
            db.add(SubscriptionPlan(**row, active=True))
            added = True
    if added:
        db.commit()


def list_active_plans(db: Session) -> list[SubscriptionPlan]:
    ensure_plans_seeded(db)
    return (db.query(SubscriptionPlan)
              .filter(SubscriptionPlan.active.is_(True))
              .order_by(SubscriptionPlan.sort_order)
              .all())


def get_plan(db: Session, code: str) -> SubscriptionPlan | None:
    ensure_plans_seeded(db)
    return db.query(SubscriptionPlan).filter(SubscriptionPlan.code == code).first()


# ── Subscriptions ─────────────────────────────────────────────────────────────
def _period_end(start: datetime, cycle: str) -> datetime:
    return start + timedelta(days=365 if cycle == CYCLE_ANNUAL else 30)


def start_trial(db: Session, tenant_id: int, plan_code: str = SOLO) -> Subscription:
    """A 14-day, no-credit-card trial created at signup (spec Part 2 `trial`).
    Idempotent per tenant — one subscription row per tenant."""
    existing = get_subscription(db, tenant_id)
    if existing:
        return existing
    plan = get_plan(db, plan_code) or get_plan(db, FREE)
    now = utcnow()
    days = plan.trial_days or 0
    sub = Subscription(
        tenant_id=tenant_id,
        plan_code=plan.code if days else FREE,
        status=STATUS_TRIALING if days else STATUS_ACTIVE,
        billing_cycle=CYCLE_MONTHLY,
        seats=plan.min_seats or 1,
        current_period_start=now,
        current_period_end=now + timedelta(days=days) if days else _period_end(now, CYCLE_MONTHLY),
        trial_end=now + timedelta(days=days) if days else None,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def get_subscription(db: Session, tenant_id: int) -> Subscription | None:
    return db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()


def get_or_create_subscription(db: Session, tenant_id: int) -> Subscription:
    """Every tenant always resolves to a subscription — legacy tenants land on Free."""
    sub = get_subscription(db, tenant_id)
    if sub:
        return sub
    now = utcnow()
    sub = Subscription(tenant_id=tenant_id, plan_code=FREE, status=STATUS_ACTIVE,
                       billing_cycle=CYCLE_MONTHLY, seats=1,
                       current_period_start=now, current_period_end=_period_end(now, CYCLE_MONTHLY))
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def downgrade_to_free(db: Session, sub: Subscription) -> Subscription:
    now = utcnow()
    sub.plan_code = FREE
    sub.status = STATUS_ACTIVE
    sub.seats = 1
    sub.trial_end = None
    sub.cancel_at_period_end = False
    sub.current_period_start = now
    sub.current_period_end = _period_end(now, CYCLE_MONTHLY)
    db.commit()
    db.refresh(sub)
    return sub


def effective_plan(db: Session, sub: Subscription) -> SubscriptionPlan:
    """The plan whose limits actually apply right now.
    An expired trial or a canceled/expired subscription falls back to Free —
    entitlements never outlive the thing that paid for them."""
    if sub.status in (STATUS_CANCELED, STATUS_EXPIRED):
        return get_plan(db, FREE)
    if sub.status == STATUS_TRIALING and sub.trial_end and sub.trial_end < utcnow():
        return get_plan(db, FREE)
    return get_plan(db, sub.plan_code) or get_plan(db, FREE)


# ── Limits + usage ────────────────────────────────────────────────────────────
_LIMIT_KEY = {KIND_RESEARCH: "research_queries_per_month", KIND_DRAFT: "drafts_per_month"}


def quota_for(plan: SubscriptionPlan, kind: str, seats: int) -> int | None:
    """Allowance for this period. None = unlimited/custom (enterprise)."""
    raw = (plan.limits or {}).get(_LIMIT_KEY[kind])
    if raw is None or raw == "custom":
        return None
    base = int(raw)
    return base * max(1, seats) if plan.per_seat else base


def count_usage(db: Session, tenant_id: int, kind: str, since: datetime) -> int:
    # Floor the window to the second: a backend whose timestamps have second precision
    # (SQLite CURRENT_TIMESTAMP) must never drop usage recorded in the same second the
    # period began. Counting one extra second in the tenant's favour is the safe error.
    window = since.replace(microsecond=0)
    return (db.query(func.count(UsageEvent.id))
              .filter(UsageEvent.tenant_id == tenant_id,
                      UsageEvent.kind == kind,
                      UsageEvent.created_at >= window)
              .scalar()) or 0


def usage_snapshot(db: Session, tenant_id: int) -> dict:
    """What the user sees on /usage and in the account page: used vs allowed."""
    sub = get_or_create_subscription(db, tenant_id)
    plan = effective_plan(db, sub)
    since = sub.current_period_start
    out = {"plan_code": plan.code, "plan_name": plan.name, "status": sub.status,
           "period_start": sub.current_period_start, "period_end": sub.current_period_end,
           "seats": sub.seats, "items": {}}
    for kind in (KIND_RESEARCH, KIND_DRAFT):
        limit = quota_for(plan, kind, sub.seats)
        used = count_usage(db, tenant_id, kind, since)
        out["items"][kind] = {
            "used": used,
            "limit": limit,                       # None = unlimited
            "remaining": None if limit is None else max(0, limit - used),
        }
    return out


class QuotaExceeded(Exception):
    """Raised when a metered action would exceed the plan's fair-use limit."""

    def __init__(self, kind: str, used: int, limit: int, plan_code: str):
        self.kind, self.used, self.limit, self.plan_code = kind, used, limit, plan_code
        super().__init__(f"{kind} limit reached ({used}/{limit}) on plan '{plan_code}'")

    def payload(self) -> dict:
        friendly = "AI research queries" if self.kind == KIND_RESEARCH else "AI drafts"
        return {
            "error": "limit_reached",
            "kind": self.kind,
            "used": self.used,
            "limit": self.limit,
            "plan": self.plan_code,
            "message": (f"You've used all {self.limit} {friendly} included in your "
                        f"{self.plan_code.replace('_', ' ')} plan this period. "
                        f"Upgrade to continue — your data and drafts are untouched."),
            "upgrade_url": "/pricing",
        }


def check_quota(db: Session, tenant_id: int, kind: str) -> None:
    """Raise QuotaExceeded if this action would exceed the plan. Never silently exceeds."""
    sub = get_or_create_subscription(db, tenant_id)
    plan = effective_plan(db, sub)
    limit = quota_for(plan, kind, sub.seats)
    if limit is None:
        return
    used = count_usage(db, tenant_id, kind, sub.current_period_start)
    if used >= limit:
        raise QuotaExceeded(kind, used, limit, plan.code)


def record_usage(db: Session, tenant_id: int, user_id: int, kind: str) -> None:
    """Record AFTER the action is committed to run — a rejected request costs nothing."""
    db.add(UsageEvent(tenant_id=tenant_id, user_id=user_id, kind=kind))
    db.commit()


def feature_enabled(db: Session, tenant_id: int, flag: str) -> bool:
    plan = effective_plan(db, get_or_create_subscription(db, tenant_id))
    return bool((plan.limits or {}).get(flag))


def diary_is_writable(db: Session, tenant_id: int) -> bool:
    """Free tier gets a read-only court diary — enforced at the API layer, not just the UI."""
    plan = effective_plan(db, get_or_create_subscription(db, tenant_id))
    return (plan.limits or {}).get("court_diary") == "full"


def vault_limit_mb(db: Session, tenant_id: int) -> int | None:
    sub = get_or_create_subscription(db, tenant_id)
    plan = effective_plan(db, sub)
    lim = (plan.limits or {})
    if "vault_mb" in lim:
        v = lim["vault_mb"]
    else:
        v = lim.get("vault_mb_per_seat")
        if isinstance(v, int):
            v = v * max(1, sub.seats)
    return None if (v is None or v == "custom") else int(v)


# ── GST ───────────────────────────────────────────────────────────────────────
def compute_gst(amount_paise: int, rate_percent: int | None = None) -> tuple[int, int, int]:
    """Prices are displayed exclusive of GST; GST is added at checkout.
    Returns (amount_paise, gst_paise, total_paise). Integer paise — no float rounding.
    NOTE: rate/place-of-supply/reverse-charge must be confirmed by a chartered accountant."""
    rate = gst_rate_percent() if rate_percent is None else rate_percent
    gst = (amount_paise * rate + 50) // 100      # round-half-up on paise
    return amount_paise, gst, amount_paise + gst


def price_paise(plan: SubscriptionPlan, cycle: str, seats: int,
                founding_member: bool = False) -> int:
    """Taxable value in paise for one billing period."""
    if founding_member and plan.code == SOLO and cycle == CYCLE_MONTHLY:
        rupees = FOUNDING_MEMBER["price_monthly_inr"]
    else:
        rupees = plan.price_annual_inr if cycle == CYCLE_ANNUAL else plan.price_monthly_inr
    if rupees is None:
        raise ValueError(f"Plan '{plan.code}' has no self-serve price (sales-led).")
    units = max(1, seats) if plan.per_seat else 1
    return int(rupees) * 100 * units


# ── Trial lifecycle (no silent auto-charge; spec Part 2 `trial.on_expiry`) ────
def run_trial_lifecycle(db: Session, now: datetime | None = None) -> dict:
    """Warn 3 days before a trial ends, and downgrade to Free when it does.

    A trial NEVER converts to a paid plan by itself — no card was taken, and Part 4
    forbids trial-to-paid conversion without explicit consent. Expiry means the tenant
    lands on Free with their data intact, not a surprise charge.
    Idempotent: notifications dedupe, and an already-Free tenant is skipped.
    """
    from app.services.notifications import notify
    from app.services.tenancy import write_audit

    now = now or utcnow()
    warned = downgraded = 0

    trials = (db.query(Subscription)
                .filter(Subscription.status == STATUS_TRIALING,
                        Subscription.trial_end.isnot(None))
                .all())
    for sub in trials:
        days_left = (sub.trial_end - now).days
        if sub.trial_end <= now:
            downgrade_to_free(db, sub)
            notify(db, tenant_id=sub.tenant_id, ntype="billing",
                   title="Your free trial has ended",
                   body=("You're now on the Free plan. Nothing was charged — we never take a card "
                         "for a trial. Your matters, drafts and diary are exactly as you left them. "
                         "Upgrade anytime to restore full limits."),
                   link="/pricing", dedupe_key=f"trial_expired:{sub.tenant_id}")
            write_audit(db, tenant_id=sub.tenant_id, user_id=0,
                        action="billing_trial_expired", entity="Subscription", entity_id=sub.id,
                        detail="downgraded to free (no charge)")
            downgraded += 1
        elif 0 <= days_left <= 3:
            notify(db, tenant_id=sub.tenant_id, ntype="billing",
                   title=f"Your trial ends in {max(1, days_left)} day(s)",
                   body=("When it ends you'll move to the Free plan automatically. "
                         "No charge, no card on file. Upgrade only if you want to keep full limits."),
                   link="/pricing", dedupe_key=f"trial_ending:{sub.tenant_id}")
            warned += 1

    return {"warned": warned, "downgraded": downgraded}


def next_invoice_number(db: Session) -> str:
    from app.models.billing import Invoice
    n = (db.query(func.count(Invoice.id)).scalar() or 0) + 1
    return f"JC-{utcnow():%Y%m}-{n:05d}"
