from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.hearing import Hearing
from app.models.user import User
from app.auth.dependencies import require_matter_write
from app.services.tenancy import (
    current_tenant_id, get_owned_case, get_owned_child, scoped_children, write_audit,
)
from app.services.entitlements import diary_write_gate
from app.schemas.hearing import HearingCreate, HearingUpdate, HearingOut

router = APIRouter()


@router.get("/", response_model=list[HearingOut])
def list_hearings(
    case_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(current_tenant_id),
):
    return (
        scoped_children(db, Hearing, tenant_id, case_id)
        .order_by(Hearing.hearing_date)
        .all()
    )


@router.post("/", response_model=HearingOut, status_code=201, dependencies=[Depends(diary_write_gate)])
def create_hearing(
    payload: HearingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    get_owned_case(payload.case_id, user.tenant_id, db)
    hearing = Hearing(**payload.model_dump())
    db.add(hearing)
    db.commit()
    db.refresh(hearing)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_hearing", entity="Hearing", entity_id=hearing.id)
    return hearing


@router.get("/{hearing_id}", response_model=HearingOut)
def get_hearing(
    hearing_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(current_tenant_id),
):
    return get_owned_child(db, Hearing, hearing_id, tenant_id, "Hearing")


@router.patch("/{hearing_id}", response_model=HearingOut, dependencies=[Depends(diary_write_gate)])
def update_hearing(
    hearing_id: int,
    payload: HearingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    hearing = get_owned_child(db, Hearing, hearing_id, user.tenant_id, "Hearing")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(hearing, field, value)
    db.commit()
    db.refresh(hearing)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_hearing", entity="Hearing", entity_id=hearing.id)
    return hearing


@router.delete("/{hearing_id}", status_code=204, dependencies=[Depends(diary_write_gate)])
def delete_hearing(
    hearing_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    hearing = get_owned_child(db, Hearing, hearing_id, user.tenant_id, "Hearing")
    db.delete(hearing)
    db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_hearing", entity="Hearing", entity_id=hearing_id)
