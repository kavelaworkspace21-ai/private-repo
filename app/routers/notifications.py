"""Notifications — in-app reminders feed + manual reminder trigger (admin)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.notification import Notification
from app.auth.dependencies import get_current_user, require_firm_admin
from app.services.notifications import run_due_reminders

router = APIRouter()


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: Optional[str]
    link: Optional[str]
    is_read: bool
    created_at: Optional[datetime]
    model_config = {"from_attributes": True}


@router.get("/", response_model=list[NotificationOut])
def list_notifications(unread_only: bool = False, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    q = db.query(Notification).filter(Notification.tenant_id == user.tenant_id)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    return q.order_by(Notification.id.desc()).limit(100).all()


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = (db.query(Notification)
         .filter(Notification.tenant_id == user.tenant_id,
                 Notification.is_read == False).count())
    return {"unread": n}


@router.post("/{note_id}/read", status_code=204)
def mark_read(note_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    note = db.get(Notification, note_id)
    if not note or note.tenant_id != user.tenant_id:
        raise HTTPException(404, "Notification not found")
    note.is_read = True
    db.commit()


@router.post("/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    (db.query(Notification)
     .filter(Notification.tenant_id == user.tenant_id, Notification.is_read == False)
     .update({Notification.is_read: True}))
    db.commit()


@router.post("/run-reminders")
def trigger_reminders(db: Session = Depends(get_db), _admin: User = Depends(require_firm_admin)):
    """Manually run the reminder scan (also runs automatically on a daily schedule)."""
    fired = run_due_reminders(db)
    return {"status": "ok", "fired": fired}
