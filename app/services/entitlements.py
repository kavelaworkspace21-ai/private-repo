"""
Entitlement enforcement — what makes a plan real (spec 3.4).

Two rules, both absolute:
  1. Never silently exceed a limit. Over quota → 402 with a plain-English payload that
     names the limit, the plan, and where to upgrade. No throttling in the dark.
  2. A rejected request costs the advocate nothing. We CHECK before doing the work and
     only RECORD once the work is actually going to happen.

Metering maps 1:1 to what the pricing page promises:
    "AI research queries"  → a research question in the assistant
    "AI drafts"            → a drafted document (drafting engine, or a chat draft)
Read-only lookups (statute browse, provisions side-panel, dashboard judgment feed)
are NOT metered — they cost us nothing and silently burning an advocate's quota on a
page load would be exactly the kind of dark pattern Part 4 forbids.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import billing as bl


def enforce_quota(db: Session, user: User, kind: str) -> None:
    """Raise 402 if this metered action would exceed the tenant's fair-use limit."""
    if not user.tenant_id:
        return                                   # no tenant → nothing to meter against
    try:
        bl.check_quota(db, user.tenant_id, kind)
    except bl.QuotaExceeded as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail=exc.payload())


def meter(db: Session, user: User, kind: str) -> None:
    """Record one unit of usage. Call only once the action is committed to run."""
    if not user.tenant_id:
        return
    bl.record_usage(db, user.tenant_id, user.id, kind)


def _upgrade_error(feature: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail={
        "error": "plan_upgrade_required",
        "feature": feature,
        "message": message,
        "upgrade_url": "/pricing",
    })


def diary_write_gate(user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> User:
    """Free tier gets a VIEW-ONLY court diary — enforced here at the API layer, not merely
    hidden in the UI (spec 3.4). Reads stay open; every mutation needs a full-diary plan."""
    if user.tenant_id and not bl.diary_is_writable(db, user.tenant_id):
        raise _upgrade_error(
            "court_diary",
            "Your Free plan includes a view-only court diary. Upgrade to Solo Advocate "
            "to add hearings, tasks and deadlines — and to get reminders that actually fire.",
        )
    return user


def require_feature(flag: str, message: str):
    """Generic feature gate (rbac, firm_audit_dashboard, reminders, sso)."""
    def _dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.tenant_id and not bl.feature_enabled(db, user.tenant_id, flag):
            raise _upgrade_error(flag, message)
        return user
    return _dep
