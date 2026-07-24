from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.fee_collected import FeeCollected
from app.models.fee_due import FeeDue
from app.models.user import User
from app.auth.dependencies import require_matter_write
from app.services.tenancy import (
    current_tenant_id, get_owned_case, get_owned_child, scoped_children, write_audit,
)
from app.schemas.fee import (
    FeeCollectedCreate, FeeCollectedUpdate, FeeCollectedOut,
    FeeDueCreate, FeeDueUpdate, FeeDueOut,
)

router = APIRouter()

# ── Fees Collected ────────────────────────────────────────

@router.get("/collected", response_model=list[FeeCollectedOut])
def list_fees_collected(
    case_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(current_tenant_id),
):
    return (
        scoped_children(db, FeeCollected, tenant_id, case_id)
        .order_by(FeeCollected.payment_date.desc())
        .all()
    )


@router.post("/collected", response_model=FeeCollectedOut, status_code=201)
def create_fee_collected(
    payload: FeeCollectedCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    get_owned_case(payload.case_id, user.tenant_id, db)
    record = FeeCollected(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_fee_collected", entity="FeeCollected", entity_id=record.id)
    return record


@router.patch("/collected/{fee_id}", response_model=FeeCollectedOut)
def update_fee_collected(
    fee_id: int,
    payload: FeeCollectedUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    record = get_owned_child(db, FeeCollected, fee_id, user.tenant_id, "Record")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_fee_collected", entity="FeeCollected", entity_id=record.id)
    return record


@router.delete("/collected/{fee_id}", status_code=204)
def delete_fee_collected(
    fee_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    record = get_owned_child(db, FeeCollected, fee_id, user.tenant_id, "Record")
    db.delete(record)
    db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_fee_collected", entity="FeeCollected", entity_id=fee_id)


# ── Fees Due ──────────────────────────────────────────────

@router.get("/due", response_model=list[FeeDueOut])
def list_fees_due(
    case_id: int | None = None,
    unpaid_only: bool = False,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(current_tenant_id),
):
    q = scoped_children(db, FeeDue, tenant_id, case_id)
    if unpaid_only:
        q = q.filter(FeeDue.is_paid == False)
    return q.order_by(FeeDue.due_date).all()


@router.post("/due", response_model=FeeDueOut, status_code=201)
def create_fee_due(
    payload: FeeDueCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    get_owned_case(payload.case_id, user.tenant_id, db)
    record = FeeDue(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_fee_due", entity="FeeDue", entity_id=record.id)
    return record


@router.patch("/due/{fee_id}", response_model=FeeDueOut)
def update_fee_due(
    fee_id: int,
    payload: FeeDueUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    record = get_owned_child(db, FeeDue, fee_id, user.tenant_id, "Record")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_fee_due", entity="FeeDue", entity_id=record.id)
    return record


@router.delete("/due/{fee_id}", status_code=204)
def delete_fee_due(
    fee_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    record = get_owned_child(db, FeeDue, fee_id, user.tenant_id, "Record")
    db.delete(record)
    db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_fee_due", entity="FeeDue", entity_id=fee_id)
