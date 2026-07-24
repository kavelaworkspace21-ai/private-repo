"""
DPDP data-principal rights request tracker (LSAI-LEGAL-05).

Users can file access/export/correction/erasure/grievance/withdrawal requests; firm admins
triage them. Every create/update is audited and tenant-scoped. (Export and erasure also have
direct self-service flows under /api/account; this tracker records and proves the obligation.)
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.data_rights import DataRightsRequest, REQUEST_TYPES, STATUSES
from app.auth.dependencies import get_current_user, require_firm_admin
from app.services.tenancy import write_audit

router = APIRouter()

RESPONSE_DAYS = 30  # target response window (placeholder — confirm with counsel/DPDP rules)


class CreateReq(BaseModel):
    request_type: str
    details: str | None = None


class UpdateReq(BaseModel):
    status: str
    resolver_note: str | None = None


def _out(r: DataRightsRequest) -> dict:
    return {"id": r.id, "request_type": r.request_type, "status": r.status,
            "details": r.details, "resolver_note": r.resolver_note,
            "deadline": r.deadline, "created_at": r.created_at, "resolved_at": r.resolved_at}


@router.post("/")
def create_request(body: CreateReq, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if body.request_type not in REQUEST_TYPES:
        raise HTTPException(422, f"request_type must be one of {REQUEST_TYPES}")
    req = DataRightsRequest(
        tenant_id=user.tenant_id, user_id=user.id, request_type=body.request_type,
        details=((body.details or "").strip() or None), status="received",
        deadline=datetime.now(timezone.utc) + timedelta(days=RESPONSE_DAYS))
    db.add(req)
    db.commit()
    db.refresh(req)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="data_rights_request", entity="DataRightsRequest",
                entity_id=req.id, detail=body.request_type)
    return _out(req)


@router.get("/mine")
def my_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(DataRightsRequest)
            .filter(DataRightsRequest.user_id == user.id)
            .order_by(DataRightsRequest.id.desc()).all())
    return [_out(r) for r in rows]


@router.get("/")
def tenant_requests(user: User = Depends(require_firm_admin), db: Session = Depends(get_db)):
    """Firm admin: all data-rights requests for this tenant."""
    rows = (db.query(DataRightsRequest)
            .filter(DataRightsRequest.tenant_id == user.tenant_id)
            .order_by(DataRightsRequest.id.desc()).all())
    return [_out(r) for r in rows]


@router.patch("/{req_id}")
def update_request(req_id: int, body: UpdateReq, user: User = Depends(require_firm_admin),
                   db: Session = Depends(get_db)):
    if body.status not in STATUSES:
        raise HTTPException(422, f"status must be one of {STATUSES}")
    req = (db.query(DataRightsRequest)
           .filter(DataRightsRequest.id == req_id,
                   DataRightsRequest.tenant_id == user.tenant_id).first())
    if not req:
        raise HTTPException(404, "Request not found")
    req.status = body.status
    if body.resolver_note is not None:
        req.resolver_note = body.resolver_note.strip() or None
    if body.status in ("completed", "rejected"):
        req.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(req)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="data_rights_update", entity="DataRightsRequest",
                entity_id=req.id, detail=body.status)
    return _out(req)
