from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.case import Case
from app.models.user import User
from app.auth.dependencies import require_matter_write
from app.services.tenancy import (
    current_tenant_id, get_owned_case, get_owned_client, write_audit,
)
from app.schemas.case import CaseCreate, CaseUpdate, CaseOut

router = APIRouter()


@router.get("/", response_model=list[CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(current_tenant_id),
):
    return (
        db.query(Case)
        .filter(Case.tenant_id == tenant_id)
        .order_by(Case.id)
        .all()
    )


@router.post("/", response_model=CaseOut, status_code=201)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    # The linked client must belong to the same tenant.
    get_owned_client(payload.client_id, user.tenant_id, db)
    case = Case(**payload.model_dump(), tenant_id=user.tenant_id)
    db.add(case)
    db.commit()
    db.refresh(case)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_case", entity="Case", entity_id=case.id)
    return case


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(current_tenant_id),
):
    return get_owned_case(case_id, tenant_id, db)


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    case = get_owned_case(case_id, user.tenant_id, db)
    data = payload.model_dump(exclude_unset=True)
    if "client_id" in data:
        get_owned_client(data["client_id"], user.tenant_id, db)
    for field, value in data.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_case", entity="Case", entity_id=case.id)
    return case


@router.delete("/{case_id}", status_code=204)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    case = get_owned_case(case_id, user.tenant_id, db)
    db.delete(case)
    db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_case", entity="Case", entity_id=case_id)
