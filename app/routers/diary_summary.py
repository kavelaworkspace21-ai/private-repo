from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.session import get_db
from app.models.diary_entry import DiaryEntry
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


# REMOVED 2026-08-04 (S5 security review): `GET /tasks`, handler `diary_tasks`.
#
# The second of two shadowed duplicates in this file, found by
# tests/test_endpoint_authorization.py::test_no_duplicate_path_and_method_registrations.
# `diary.router` is included first and registers the same GET /api/diary/tasks, so this
# handler never ran.
#
# Unlike the /deadlines duplicate it was NOT a security hole — it took current_tenant_id and
# filtered Case.tenant_id correctly. It is removed anyway, because a shadowed handler is dead
# code that goes live the moment route ordering shifts, and reviewing it teaches you nothing
# about what the app actually serves. Behaviour is unchanged: the frontend calls
# /api/diary/tasks with `pending_only=` and `case_id=`, parameters only diary.list_tasks
# accepts, so it has always been talking to that handler. TaskSummary existed solely for this
# response and went with it.


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


# REMOVED 2026-08-04 (S5 security review): `GET /deadlines`, handler `diary_deadlines`.
#
# It took NO authentication dependency and applied NO tenant filter. Its whole dependency tree
# was `get_db`. It queried FilingDeadline joined to Case across the entire table and returned
# every firm's filing deadlines together with their case titles, to anyone who asked.
#
# It was never reachable: `diary.router` is included before `diary_summary.router` in main.py
# and registers the same `GET /api/diary/deadlines`, so FastAPI matched the protected handler
# first — an unauthenticated request returned 401, verified. But the only thing standing
# between every tenant's matter data and the public internet was the ORDER OF TWO LINES in
# main.py. Moving an include, or deleting the route that shadowed it, would have published it
# silently, and no test would have failed.
#
# Deleted rather than secured: nothing consumed it. The frontend calls /api/diary/deadlines
# with `unfiled_only=` and `case_id=`, parameters only diary.list_deadlines accepts, so it has
# always been talking to the protected handler. DeadlineSummary existed solely for this
# response and went with it. Every other endpoint in this file takes
# `tenant_id: int = Depends(current_tenant_id)` and filters `Case.tenant_id == tenant_id`;
# this one was an outlier, not a design decision.
#
# tests/test_endpoint_authorization.py now enumerates every route and fails on any that is
# neither protected nor explicitly listed as public, so a shadowed handler cannot hide again.
