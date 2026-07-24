"""
Activity tracker — logs user actions and builds context strings for the agent.
"""
from __future__ import annotations
import logging
from datetime import timedelta

from app.util.time import utcnow
from typing import Optional
from sqlalchemy.orm import Session

from app.models.user_activity import UserActivity

logger = logging.getLogger(__name__)

# ── Log a single activity ─────────────────────────────────────────────────────
def log_activity(
    db: Session,
    user_id: int,
    action_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    entity_label: Optional[str] = None,
    meta: Optional[dict] = None,
):
    """
    Record a user activity. Fire-and-forget — errors are logged but not raised.
    action_type examples:
        "view_case", "create_case", "update_case"
        "view_client", "create_client"
        "create_hearing", "view_hearing"
        "view_document", "upload_document"
        "create_diary", "create_task"
        "chat_query", "draft_document"
        "login", "page_view"
    """
    try:
        activity = UserActivity(
            user_id=user_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label,
            meta=meta or {},
        )
        db.add(activity)
        db.commit()
    except Exception as e:
        logger.warning(f"Activity log failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass


# ── Build context string for agent ───────────────────────────────────────────
def build_activity_context(db: Session, user_id: int, limit: int = 15) -> str:
    """
    Fetch the user's recent activities and format them as an agent context block.
    The agent uses this to give personalised, contextually relevant responses.
    """
    try:
        since = utcnow() - timedelta(days=7)
        activities = (
            db.query(UserActivity)
            .filter(
                UserActivity.user_id == user_id,
                UserActivity.created_at >= since,
            )
            .order_by(UserActivity.created_at.desc())
            .limit(limit)
            .all()
        )

        if not activities:
            return ""

        lines = []
        for a in activities:
            ts = a.created_at.strftime("%d %b %Y %H:%M") if a.created_at else "recently"
            label = f' — "{a.entity_label}"' if a.entity_label else ""
            entity = f" [{a.entity_type} #{a.entity_id}]" if a.entity_id else ""
            lines.append(f"• [{ts}] {a.action_type}{label}{entity}")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Activity context build failed: {e}")
        return ""


# ── Pre-built log helpers ────────────────────────────────────────────────────
def log_chat(db: Session, user_id: int, conversation_id: int, preview: str):
    log_activity(db, user_id, "chat_query",
                 entity_type="conversation", entity_id=conversation_id,
                 entity_label=preview[:80])


def log_draft(db: Session, user_id: int, doc_type: str):
    log_activity(db, user_id, "draft_document",
                 entity_type="draft", entity_label=doc_type)


def log_case_view(db: Session, user_id: int, case_id: int, case_label: str):
    log_activity(db, user_id, "view_case",
                 entity_type="case", entity_id=case_id, entity_label=case_label)


def log_hearing(db: Session, user_id: int, hearing_id: int, label: str):
    log_activity(db, user_id, "create_hearing",
                 entity_type="hearing", entity_id=hearing_id, entity_label=label)
