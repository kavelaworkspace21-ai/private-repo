"""
Notifications + reminder engine (Phase A · A1).

- `notify()` always writes an in-app Notification (durable record) and, if SMTP is
  configured, additionally emails the recipient. Idempotent via `dedupe_key`.
- `run_due_reminders()` scans hearings + filing deadlines across all tenants and fires
  reminders for the day-before / day-of (hearings) and 3-day / 1-day / day-of (deadlines).
  Each fire writes an AuditLog row. Safe to run repeatedly (won't double-notify).
"""
import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User
from app.models.case import Case
from app.models.diary_entry import DiaryEntry
from app.models.filing_deadline import FilingDeadline
from app.models.audit import AuditLog
from app.services.email import send_email as _send_email, email_enabled  # noqa: F401

logger = logging.getLogger(__name__)


def _tenant_recipient(db: Session, tenant_id: int) -> User | None:
    return (db.query(User)
            .filter(User.tenant_id == tenant_id, User.is_active == True)
            .order_by(User.id).first())


def notify(db: Session, *, tenant_id: int, title: str, body: str = "",
           link: str = "", dedupe_key: str | None = None,
           ntype: str = "reminder", user_id: int | None = None) -> Notification | None:
    """Create an in-app notification (idempotent on dedupe_key) + optional email."""
    if dedupe_key:
        exists = (db.query(Notification)
                  .filter(Notification.tenant_id == tenant_id,
                          Notification.dedupe_key == dedupe_key).first())
        if exists:
            return None

    recipient = _tenant_recipient(db, tenant_id) if user_id is None else db.get(User, user_id)
    note = Notification(
        tenant_id=tenant_id, user_id=(recipient.id if recipient else user_id),
        type=ntype, title=title, body=body, link=link, dedupe_key=dedupe_key,
    )
    if recipient and recipient.email:
        note.emailed = _send_email(recipient.email, title, body)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


# ── Reminder scan ───────────────────────────────────────────────────────────────
def run_due_reminders(db: Session, today: date | None = None) -> int:
    """Fire reminders for upcoming hearings + filing deadlines. Returns count fired."""
    today = today or date.today()
    fired = 0

    # Hearings: day-before and day-of
    for offset, label in ((1, "tomorrow"), (0, "today")):
        target = today + timedelta(days=offset)
        rows = (db.query(DiaryEntry, Case.title, Case.tenant_id)
                .join(Case, DiaryEntry.case_id == Case.id)
                .filter(DiaryEntry.hearing_date == target).all())
        for entry, case_title, tenant_id in rows:
            key = f"hearing:{entry.id}:{target.isoformat()}"
            n = notify(
                db, tenant_id=tenant_id,
                title=f"Hearing {label}: {case_title}",
                body=f"{case_title} — {entry.court_name} on {target.strftime('%d %b %Y')}.",
                link="/diary", dedupe_key=key, ntype="hearing_reminder",
            )
            if n:
                _audit(db, tenant_id, "reminder_fired", "DiaryEntry", entry.id, key)
                fired += 1

    # Filing deadlines (unfiled): 3-day, 1-day, day-of
    for offset, label in ((3, "in 3 days"), (1, "tomorrow"), (0, "today")):
        target = today + timedelta(days=offset)
        rows = (db.query(FilingDeadline, Case.title, Case.tenant_id)
                .join(Case, FilingDeadline.case_id == Case.id)
                .filter(FilingDeadline.deadline_date == target,
                        FilingDeadline.is_filed == False).all())
        for dl, case_title, tenant_id in rows:
            key = f"deadline:{dl.id}:{target.isoformat()}"
            n = notify(
                db, tenant_id=tenant_id,
                title=f"Deadline {label}: {dl.title}",
                body=f"{dl.title} ({case_title}) is due {target.strftime('%d %b %Y')}.",
                link="/diary", dedupe_key=key, ntype="deadline_reminder",
            )
            if n:
                _audit(db, tenant_id, "reminder_fired", "FilingDeadline", dl.id, key)
                fired += 1

    return fired


def _audit(db: Session, tenant_id: int, action: str, entity: str, entity_id: int, detail: str):
    try:
        db.add(AuditLog(tenant_id=tenant_id, user_id=0, action=action,
                        entity=entity, entity_id=entity_id, detail=detail))
        db.commit()
    except Exception:
        db.rollback()
