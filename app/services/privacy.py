"""
Data-protection foundation (DPDP Act 2023 + SC draft AI-in-Courts Regs 2026, reg. 10/47-48).

Principles the product commits to:
  • Purpose limitation — client data is used only to serve that advocate's own matters.
  • Data minimisation — we store/transmit the minimum needed.
  • No training on client data — client/matter data is NEVER used to train or fine-tune models.
  • Consent is recorded and auditable (ConsentRecord).
  • Data-principal rights — access/export (here) and erasure (account deletion).
"""
from sqlalchemy.orm import Session
from app.models.consent import ConsentRecord

# Current policy versions (bump when the policy text changes; a new consent is then recorded).
TERMS_VERSION = "2026-06-20"
PRIVACY_VERSION = "2026-06-20"
NOTICE_VERSION = "2026-06-23"  # the consent-notice/screen version (bump to force re-consent)
CONSENT_TYPES = ("terms_of_service", "privacy_policy")

NO_TRAINING_STATEMENT = (
    "Client and matter data is used only to provide the service to the owning advocate. "
    "It is never used to train or fine-tune AI models, and is never shared across firms."
)

# Conservative retention policy. Legal/matter data is intentionally retained for the
# advocate's needs (limitation periods run for years) and is removed only on an erasure
# request (DELETE /api/account). Only genuinely transient data is auto-purged.
RETENTION_POLICY = {
    "matter_data": "Retained until the advocate deletes it or requests account erasure "
                   "(legal limitation periods require long retention).",
    "audit_logs": "Retained for accountability; not auto-deleted (removed only on erasure).",
    "read_notifications": "Auto-purged 90 days after being read.",
}
READ_NOTIFICATION_RETENTION_DAYS = 90


def purge_old_read_notifications(db, days: int = READ_NOTIFICATION_RETENTION_DAYS) -> int:
    """Delete notifications that were READ and are older than `days`. Returns count deleted."""
    from datetime import datetime, timedelta, timezone
    from app.models.notification import Notification
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    n = (db.query(Notification)
         .filter(Notification.is_read == True, Notification.created_at < cutoff)
         .delete(synchronize_session=False))
    db.commit()
    return n


def has_current_consent(db: Session, user_id: int) -> bool:
    """Has this user granted privacy consent at the CURRENT policy version?

    Single source of truth — both `/api/auth/needs-consent` (what the UI shows) and the
    AI-boundary gate (what actually blocks) call this, so the banner and the enforcement
    can never drift apart. Bumping PRIVACY_VERSION invalidates prior consent by design.

    Self-registered users get consent recorded at registration. Firm-INVITED members do
    not — an admin created their account, so they have granted nothing until they accept.
    """
    return db.query(ConsentRecord).filter(
        ConsentRecord.user_id == user_id,
        ConsentRecord.consent_type == "privacy_policy",
        ConsentRecord.policy_version == PRIVACY_VERSION,
        ConsentRecord.granted == True,          # noqa: E712 — SQL boolean, not Python
        ConsentRecord.withdrawn_at.is_(None),   # withdrawal stops authorising immediately
    ).first() is not None


# What the AI consent authorises. Recorded on the grant so the record is purpose-limited
# rather than a bare "accepted v2026-06-20".
AI_PURPOSE = "ai_processing"
AI_SCOPE = "matter_text_and_uploads_to_external_model"


def withdraw_consent(db: Session, *, user_id: int, consent_type: str = "privacy_policy") -> int:
    """Withdraw a user's consent. Returns the number of grants withdrawn.

    Marks rather than deletes: the grant stays as evidence that consent existed while it was
    relied on (erasing it would destroy the very audit trail DPDP requires), but it stops
    authorising from this moment — `has_current_consent` filters on `withdrawn_at IS NULL`,
    and the AI gate reads it per request, so the next AI call is refused. Caller commits.
    """
    from app.util.time import utcnow
    return (db.query(ConsentRecord)
            .filter(ConsentRecord.user_id == user_id,
                    ConsentRecord.consent_type == consent_type,
                    ConsentRecord.granted == True,        # noqa: E712
                    ConsentRecord.withdrawn_at.is_(None))
            .update({"withdrawn_at": utcnow()}, synchronize_session=False))


def record_consents(db: Session, *, tenant_id: int, user_id: int, source_ip: str | None,
                    granted: bool = True, user_agent: str | None = None,
                    acceptance_source: str = "registration") -> None:
    """Write one ConsentRecord per consent type at the current policy versions, with a
    provable receipt (source IP, user-agent, acceptance source)."""
    versions = {"terms_of_service": TERMS_VERSION, "privacy_policy": PRIVACY_VERSION}
    for ctype in CONSENT_TYPES:
        db.add(ConsentRecord(
            tenant_id=tenant_id, user_id=user_id, consent_type=ctype,
            policy_version=versions[ctype], granted=granted, source_ip=source_ip,
            user_agent=(user_agent[:400] if user_agent else None),
            acceptance_source=acceptance_source,
            # Only the privacy consent authorises AI processing, so only it carries the
            # AI purpose/scope. Recording it on terms_of_service would overstate the grant.
            purpose=(AI_PURPOSE if ctype == "privacy_policy" else None),
            scope=(AI_SCOPE if ctype == "privacy_policy" else None),
        ))
    # caller commits
