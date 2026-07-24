"""
Audit log visibility (CLAUDE.md §9 "audit dashboard data"; SC draft AI-in-Courts Regs 2026
reg. 9 auditability & oversight).

Firm admins can review who-did-what within THEIR tenant. Strictly tenant-scoped and read-only;
the audit trail itself is never editable from the API.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.audit import AuditLog
from app.auth.dependencies import require_firm_admin

router = APIRouter()


class AuditOut(BaseModel):
    id: int
    user_id: int
    action: str
    entity: str
    entity_id: Optional[int]
    detail: Optional[str]
    created_at: Optional[datetime]
    model_config = {"from_attributes": True}


@router.get("/", response_model=list[AuditOut])
def list_audit(action: Optional[str] = None, entity: Optional[str] = None,
               limit: int = Query(100, le=500),
               admin: User = Depends(require_firm_admin), db: Session = Depends(get_db)):
    q = db.query(AuditLog).filter(AuditLog.tenant_id == admin.tenant_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if entity:
        q = q.filter(AuditLog.entity == entity)
    return q.order_by(AuditLog.id.desc()).limit(limit).all()
