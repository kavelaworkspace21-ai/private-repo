"""
Tenancy + audit helpers (CLAUDE.md section 2.8 / 5).

Every business query MUST go through a tenant-scoped accessor so one firm can never
read another firm's data. Children (hearings, fees, documents, diary items) are
reached only via a tenant-scoped Case, which enforces isolation transitively.
"""
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.case import Case
from app.models.client import Client
from app.models.audit import AuditLog


def current_tenant_id(user: User = Depends(get_current_user)) -> int:
    if not user.tenant_id:
        raise HTTPException(403, "User is not attached to a tenant")
    return user.tenant_id


def get_owned_case(case_id: int, tenant_id: int, db: Session) -> Case:
    """Return a Case only if it belongs to the tenant, else 404 (no info leak)."""
    case = db.get(Case, case_id)
    if not case or case.tenant_id != tenant_id:
        raise HTTPException(404, "Case not found")
    return case


def get_owned_client(client_id: int, tenant_id: int, db: Session) -> Client:
    client = db.get(Client, client_id)
    if not client or client.tenant_id != tenant_id:
        raise HTTPException(404, "Client not found")
    return client


def scoped_children(db: Session, model, tenant_id: int, case_id: int | None = None):
    """
    Query a child model (Hearing, FeeDue, DiaryEntry, …) scoped to the tenant by
    joining through its parent Case. Optionally narrow to a single case_id (verified).
    """
    q = db.query(model).join(Case, model.case_id == Case.id).filter(
        Case.tenant_id == tenant_id
    )
    if case_id is not None:
        q = q.filter(model.case_id == case_id)
    return q


def get_owned_child(db: Session, model, obj_id: int, tenant_id: int, label: str):
    """Fetch a child row only if its parent Case belongs to the tenant, else 404."""
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{label} not found")
    case = db.get(Case, obj.case_id)
    if not case or case.tenant_id != tenant_id:
        raise HTTPException(404, f"{label} not found")
    return obj


def write_audit(db: Session, *, tenant_id: int, user_id: int, action: str,
                entity: str, entity_id: int | None = None, detail: str | None = None):
    """Record a mutation. Never raises into the request path."""
    try:
        db.add(AuditLog(tenant_id=tenant_id, user_id=user_id, action=action,
                        entity=entity, entity_id=entity_id, detail=detail))
        db.commit()
    except Exception:
        db.rollback()
