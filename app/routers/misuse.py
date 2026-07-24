"""
Misuse / abuse reporting (LSAI-LEGAL-16).

Any authenticated user can report misuse, abuse, security concerns, or objectionable content.
Firm admins triage reports. Every create/update is audited and tenant-scoped. Required for safe
operation and app-store compliance (a clear, in-product way to report abuse).
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.misuse_report import MisuseReport, CATEGORIES, STATUSES
from app.auth.dependencies import get_current_user, require_firm_admin
from app.services.tenancy import write_audit

router = APIRouter()


class CreateReport(BaseModel):
    category: str
    subject: str
    details: str | None = None


class UpdateReport(BaseModel):
    status: str
    resolver_note: str | None = None


def _out(r: MisuseReport) -> dict:
    return {"id": r.id, "category": r.category, "subject": r.subject, "details": r.details,
            "status": r.status, "resolver_note": r.resolver_note,
            "created_at": r.created_at, "resolved_at": r.resolved_at}


@router.post("/")
def create_report(body: CreateReport, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if body.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    if not body.subject.strip():
        raise HTTPException(422, "subject is required")
    r = MisuseReport(tenant_id=user.tenant_id, reporter_user_id=user.id,
                     category=body.category, subject=body.subject.strip(),
                     details=((body.details or "").strip() or None), status="received")
    db.add(r)
    db.commit()
    db.refresh(r)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="misuse_report", entity="MisuseReport", entity_id=r.id, detail=body.category)
    return _out(r)


@router.get("/mine")
def my_reports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(MisuseReport).filter(MisuseReport.reporter_user_id == user.id)
            .order_by(MisuseReport.id.desc()).all())
    return [_out(r) for r in rows]


@router.get("/")
def tenant_reports(user: User = Depends(require_firm_admin), db: Session = Depends(get_db)):
    rows = (db.query(MisuseReport).filter(MisuseReport.tenant_id == user.tenant_id)
            .order_by(MisuseReport.id.desc()).all())
    return [_out(r) for r in rows]


@router.patch("/{report_id}")
def update_report(report_id: int, body: UpdateReport,
                  user: User = Depends(require_firm_admin), db: Session = Depends(get_db)):
    if body.status not in STATUSES:
        raise HTTPException(422, f"status must be one of {STATUSES}")
    r = (db.query(MisuseReport).filter(MisuseReport.id == report_id,
                                       MisuseReport.tenant_id == user.tenant_id).first())
    if not r:
        raise HTTPException(404, "Report not found")
    r.status = body.status
    if body.resolver_note is not None:
        r.resolver_note = body.resolver_note.strip() or None
    if body.status in ("actioned", "dismissed"):
        r.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(r)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="misuse_update", entity="MisuseReport", entity_id=r.id, detail=body.status)
    return _out(r)
