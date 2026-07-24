from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.session import get_db
from app.models.diary_entry import DiaryEntry
from app.models.diary_task import DiaryTask
from app.models.filing_deadline import FilingDeadline
from app.models.case import Case
from app.services.tenancy import current_tenant_id

router = APIRouter()


class HearingSummary(BaseModel):
    id: int
    case_id: int
    case_title: str
    court_name: str
    court_room: Optional[str]
    stage: str
    outcome: str
    hearing_date: date

    model_config = {"from_attributes": True}


class TaskSummary(BaseModel):
    id: int
    case_id: int
    case_title: str
    title: str
    due_date: Optional[date]
    is_overdue: bool

    model_config = {"from_attributes": True}


class DeadlineSummary(BaseModel):
    id: int
    case_id: int
    case_title: str
    title: str
    deadline_date: date
    is_overdue: bool

    model_config = {"from_attributes": True}


class DiaryTodayResponse(BaseModel):
    today: list[HearingSummary]
    upcoming: list[HearingSummary]


@router.get("/today", response_model=DiaryTodayResponse)
def diary_today(db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    today = date.today()
    week_end = today + timedelta(days=7)

    today_entries = (
        db.query(DiaryEntry, Case.title)
        .join(Case, DiaryEntry.case_id == Case.id)
        .filter(Case.tenant_id == tenant_id, DiaryEntry.hearing_date == today)
        .order_by(DiaryEntry.hearing_time)
        .all()
    )

    upcoming_entries = (
        db.query(DiaryEntry, Case.title)
        .join(Case, DiaryEntry.case_id == Case.id)
        .filter(Case.tenant_id == tenant_id,
                DiaryEntry.hearing_date > today, DiaryEntry.hearing_date <= week_end)
        .order_by(DiaryEntry.hearing_date)
        .all()
    )

    def to_summary(entry, case_title):
        return HearingSummary(
            id=entry.id,
            case_id=entry.case_id,
            case_title=case_title,
            court_name=entry.court_name,
            court_room=entry.court_room,
            stage=entry.stage.value,
            outcome=entry.outcome.value,
            hearing_date=entry.hearing_date,
        )

    return DiaryTodayResponse(
        today=[to_summary(e, t) for e, t in today_entries],
        upcoming=[to_summary(e, t) for e, t in upcoming_entries],
    )


@router.get("/tasks", response_model=list[TaskSummary])
def diary_tasks(db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    today = date.today()
    rows = (
        db.query(DiaryTask, Case.title)
        .join(Case, DiaryTask.case_id == Case.id)
        .filter(Case.tenant_id == tenant_id, DiaryTask.is_completed == False)
        .order_by(DiaryTask.due_date)
        .all()
    )
    result = []
    for task, case_title in rows:
        # compute overdue live so it stays fresh without a background job
        overdue = bool(task.due_date and task.due_date < today)
        result.append(TaskSummary(
            id=task.id,
            case_id=task.case_id,
            case_title=case_title,
            title=task.title,
            due_date=task.due_date,
            is_overdue=overdue,
        ))
    return result


class MonthlyHearings(BaseModel):
    labels: list[str]   # e.g. ["Jan", "Feb", ...]
    counts: list[int]   # hearings per month, aligned with labels


@router.get("/analytics/monthly-hearings", response_model=MonthlyHearings)
def monthly_hearings(months: int = 6, db: Session = Depends(get_db),
                     tenant_id: int = Depends(current_tenant_id)):
    """Hearing counts for the trailing `months` calendar months (oldest → newest)."""
    months = max(1, min(months, 12))
    today = date.today()

    # Build the list of (year, month) buckets ending with the current month
    buckets: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(months):
        buckets.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    buckets.reverse()

    MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    window_start = date(buckets[0][0], buckets[0][1], 1)
    rows = (
        db.query(DiaryEntry.hearing_date)
        .join(Case, DiaryEntry.case_id == Case.id)
        .filter(Case.tenant_id == tenant_id, DiaryEntry.hearing_date >= window_start)
        .all()
    )

    tally: dict[tuple[int, int], int] = {b: 0 for b in buckets}
    for (hd,) in rows:
        key = (hd.year, hd.month)
        if key in tally:
            tally[key] += 1

    return MonthlyHearings(
        labels=[MONTH_ABBR[mo] for (_, mo) in buckets],
        counts=[tally[b] for b in buckets],
    )


@router.get("/deadlines", response_model=list[DeadlineSummary])
def diary_deadlines(db: Session = Depends(get_db)):
    today = date.today()
    week_end = today + timedelta(days=7)
    rows = (
        db.query(FilingDeadline, Case.title)
        .join(Case, FilingDeadline.case_id == Case.id)
        .filter(FilingDeadline.is_filed == False, FilingDeadline.deadline_date <= week_end)
        .order_by(FilingDeadline.deadline_date)
        .all()
    )
    result = []
    for dl, case_title in rows:
        overdue = dl.deadline_date < today
        result.append(DeadlineSummary(
            id=dl.id,
            case_id=dl.case_id,
            case_title=case_title,
            title=dl.title,
            deadline_date=dl.deadline_date,
            is_overdue=overdue,
        ))
    return result
