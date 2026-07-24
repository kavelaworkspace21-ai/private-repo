from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.diary_entry import DiaryEntry
from app.models.diary_task import DiaryTask
from app.models.filing_deadline import FilingDeadline
from app.models.opposing_counsel import OpposingCounsel
from app.models.user import User
from app.auth.dependencies import require_matter_write
from app.services.tenancy import (
    current_tenant_id, get_owned_case, get_owned_child, scoped_children, write_audit,
)
from app.services.entitlements import diary_write_gate
from app.schemas.diary import (
    DiaryEntryCreate, DiaryEntryUpdate, DiaryEntryOut,
    DiaryTaskCreate, DiaryTaskUpdate, DiaryTaskOut,
    FilingDeadlineCreate, FilingDeadlineUpdate, FilingDeadlineOut,
    OpposingCounselCreate, OpposingCounselUpdate, OpposingCounselOut,
)

router = APIRouter()

# ── Diary Entries ─────────────────────────────────────────

@router.get("/entries", response_model=list[DiaryEntryOut])
def list_diary_entries(case_id: int | None = None, db: Session = Depends(get_db),
                       tenant_id: int = Depends(current_tenant_id)):
    return scoped_children(db, DiaryEntry, tenant_id, case_id).order_by(
        DiaryEntry.hearing_date.desc()).all()


@router.post("/entries", response_model=DiaryEntryOut, status_code=201, dependencies=[Depends(diary_write_gate)])
def create_diary_entry(payload: DiaryEntryCreate, db: Session = Depends(get_db),
                       user: User = Depends(require_matter_write)):
    get_owned_case(payload.case_id, user.tenant_id, db)
    entry = DiaryEntry(**payload.model_dump())
    db.add(entry); db.commit(); db.refresh(entry)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_diary", entity="DiaryEntry", entity_id=entry.id)
    return entry


@router.get("/entries/{entry_id}", response_model=DiaryEntryOut)
def get_diary_entry(entry_id: int, db: Session = Depends(get_db),
                    tenant_id: int = Depends(current_tenant_id)):
    return get_owned_child(db, DiaryEntry, entry_id, tenant_id, "Entry")


@router.patch("/entries/{entry_id}", response_model=DiaryEntryOut, dependencies=[Depends(diary_write_gate)])
def update_diary_entry(entry_id: int, payload: DiaryEntryUpdate, db: Session = Depends(get_db),
                       user: User = Depends(require_matter_write)):
    entry = get_owned_child(db, DiaryEntry, entry_id, user.tenant_id, "Entry")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    db.commit(); db.refresh(entry)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_entry", entity="DiaryEntry", entity_id=entry.id)
    return entry


@router.delete("/entries/{entry_id}", status_code=204, dependencies=[Depends(diary_write_gate)])
def delete_diary_entry(entry_id: int, db: Session = Depends(get_db),
                       user: User = Depends(require_matter_write)):
    entry = get_owned_child(db, DiaryEntry, entry_id, user.tenant_id, "Entry")
    eid = entry.id
    db.delete(entry); db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_entry", entity="DiaryEntry", entity_id=eid)


# ── Tasks ─────────────────────────────────────────────────

@router.get("/tasks", response_model=list[DiaryTaskOut])
def list_tasks(case_id: int | None = None, pending_only: bool = False,
               db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    q = scoped_children(db, DiaryTask, tenant_id, case_id)
    if pending_only:
        q = q.filter(DiaryTask.is_completed == False)
    return q.order_by(DiaryTask.due_date).all()


@router.post("/tasks", response_model=DiaryTaskOut, status_code=201, dependencies=[Depends(diary_write_gate)])
def create_task(payload: DiaryTaskCreate, db: Session = Depends(get_db),
                user: User = Depends(require_matter_write)):
    get_owned_case(payload.case_id, user.tenant_id, db)
    task = DiaryTask(**payload.model_dump())
    db.add(task); db.commit(); db.refresh(task)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_task", entity="DiaryTask", entity_id=task.id)
    return task


@router.patch("/tasks/{task_id}", response_model=DiaryTaskOut, dependencies=[Depends(diary_write_gate)])
def update_task(task_id: int, payload: DiaryTaskUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_matter_write)):
    task = get_owned_child(db, DiaryTask, task_id, user.tenant_id, "Task")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit(); db.refresh(task)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_task", entity="DiaryTask", entity_id=task.id)
    return task


@router.delete("/tasks/{task_id}", status_code=204, dependencies=[Depends(diary_write_gate)])
def delete_task(task_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_matter_write)):
    task = get_owned_child(db, DiaryTask, task_id, user.tenant_id, "Task")
    tid = task.id
    db.delete(task); db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_task", entity="DiaryTask", entity_id=tid)


# ── Filing Deadlines ──────────────────────────────────────

@router.get("/deadlines", response_model=list[FilingDeadlineOut])
def list_deadlines(case_id: int | None = None, unfiled_only: bool = False,
                   db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    q = scoped_children(db, FilingDeadline, tenant_id, case_id)
    if unfiled_only:
        q = q.filter(FilingDeadline.is_filed == False)
    return q.order_by(FilingDeadline.deadline_date).all()


@router.post("/deadlines", response_model=FilingDeadlineOut, status_code=201, dependencies=[Depends(diary_write_gate)])
def create_deadline(payload: FilingDeadlineCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_matter_write)):
    get_owned_case(payload.case_id, user.tenant_id, db)
    dl = FilingDeadline(**payload.model_dump())
    db.add(dl); db.commit(); db.refresh(dl)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_deadline", entity="FilingDeadline", entity_id=dl.id)
    return dl


@router.patch("/deadlines/{dl_id}", response_model=FilingDeadlineOut, dependencies=[Depends(diary_write_gate)])
def update_deadline(dl_id: int, payload: FilingDeadlineUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_matter_write)):
    dl = get_owned_child(db, FilingDeadline, dl_id, user.tenant_id, "Deadline")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dl, field, value)
    db.commit(); db.refresh(dl)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_deadline", entity="FilingDeadline", entity_id=dl.id)
    return dl


@router.delete("/deadlines/{dl_id}", status_code=204, dependencies=[Depends(diary_write_gate)])
def delete_deadline(dl_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_matter_write)):
    dl = get_owned_child(db, FilingDeadline, dl_id, user.tenant_id, "Deadline")
    did = dl.id
    db.delete(dl); db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_deadline", entity="FilingDeadline", entity_id=did)


# ── Opposing Counsel ──────────────────────────────────────

@router.get("/opposing-counsel", response_model=list[OpposingCounselOut])
def list_opposing_counsel(case_id: int | None = None, db: Session = Depends(get_db),
                          tenant_id: int = Depends(current_tenant_id)):
    return scoped_children(db, OpposingCounsel, tenant_id, case_id).order_by(
        OpposingCounsel.id).all()


@router.post("/opposing-counsel", response_model=OpposingCounselOut, status_code=201, dependencies=[Depends(diary_write_gate)])
def create_opposing_counsel(payload: OpposingCounselCreate, db: Session = Depends(get_db),
                            user: User = Depends(require_matter_write)):
    get_owned_case(payload.case_id, user.tenant_id, db)
    record = OpposingCounsel(**payload.model_dump())
    db.add(record); db.commit(); db.refresh(record)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_opposing_counsel", entity="OpposingCounsel", entity_id=record.id)
    return record


@router.patch("/opposing-counsel/{oc_id}", response_model=OpposingCounselOut, dependencies=[Depends(diary_write_gate)])
def update_opposing_counsel(oc_id: int, payload: OpposingCounselUpdate, db: Session = Depends(get_db),
                            user: User = Depends(require_matter_write)):
    record = get_owned_child(db, OpposingCounsel, oc_id, user.tenant_id, "Record")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit(); db.refresh(record)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_opposing_counsel", entity="OpposingCounsel", entity_id=record.id)
    return record


@router.delete("/opposing-counsel/{oc_id}", status_code=204, dependencies=[Depends(diary_write_gate)])
def delete_opposing_counsel(oc_id: int, db: Session = Depends(get_db),
                            user: User = Depends(require_matter_write)):
    record = get_owned_child(db, OpposingCounsel, oc_id, user.tenant_id, "Record")
    rid = record.id
    db.delete(record); db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_opposing_counsel", entity="OpposingCounsel", entity_id=rid)
