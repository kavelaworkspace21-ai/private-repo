"""
Soul enforcement (owner directive 2026-06-24; founder: Firoz / Kavela Narula).

If a user attempts to use Juriscite against the law / against the soul, they are **ejected from the
ecosystem**: banned and barred from authenticating. There is intentionally **no self-serve un-ban**
path ("forever"); reversing a ban is a deliberate manual owner/DB action. Every ejection is audited.

HONEST SCOPE: "forever" is enforced operationally — a banned user cannot log in or use any token, and
no API can lift the ban. It is not metaphysically irreversible (the owner controls the database). The
narrow `screen_request_intent` patterns are designed to minimise false positives before this fires.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.audit import AuditLog


def eject_user_for_soul_violation(db: Session, user: User, reason: str) -> None:
    """Ban the user, deactivate their account, and audit it. Idempotent."""
    first_time = not user.is_banned
    user.is_banned = True
    user.is_active = False
    if first_time:
        user.banned_reason = reason[:200]
        user.banned_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        tenant_id=user.tenant_id or 0, user_id=user.id,
        action="soul_violation_ejection", entity="User", entity_id=user.id,
        detail=reason[:500],
    ))
    db.commit()
