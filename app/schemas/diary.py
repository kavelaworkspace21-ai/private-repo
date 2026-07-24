from pydantic import BaseModel
from typing import Optional
from datetime import date, time, datetime
from app.models.diary_entry import HearingStage, HearingOutcome


class DiaryEntryCreate(BaseModel):
    case_id: int
    hearing_date: date
    hearing_time: Optional[time] = None
    court_name: str
    court_room: Optional[str] = None
    stage: HearingStage = HearingStage.other
    outcome: HearingOutcome = HearingOutcome.pending
    adjournment_reason: Optional[str] = None
    next_date: Optional[date] = None
    order_notes: Optional[str] = None


class DiaryEntryUpdate(BaseModel):
    hearing_date: Optional[date] = None
    hearing_time: Optional[time] = None
    court_name: Optional[str] = None
    court_room: Optional[str] = None
    stage: Optional[HearingStage] = None
    outcome: Optional[HearingOutcome] = None
    adjournment_reason: Optional[str] = None
    next_date: Optional[date] = None
    order_notes: Optional[str] = None


class DiaryEntryOut(BaseModel):
    id: int
    case_id: int
    hearing_date: date
    hearing_time: Optional[time]
    court_name: str
    court_room: Optional[str]
    stage: HearingStage
    outcome: HearingOutcome
    adjournment_reason: Optional[str]
    next_date: Optional[date]
    order_notes: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DiaryTaskCreate(BaseModel):
    case_id: int
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None


class DiaryTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[date] = None
    is_completed: Optional[bool] = None


class DiaryTaskOut(BaseModel):
    id: int
    case_id: int
    title: str
    description: Optional[str]
    due_date: Optional[date]
    is_completed: bool
    is_overdue: bool
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class FilingDeadlineCreate(BaseModel):
    case_id: int
    title: str
    deadline_date: date
    notes: Optional[str] = None


class FilingDeadlineUpdate(BaseModel):
    title: Optional[str] = None
    deadline_date: Optional[date] = None
    is_filed: Optional[bool] = None
    notes: Optional[str] = None


class FilingDeadlineOut(BaseModel):
    id: int
    case_id: int
    title: str
    deadline_date: date
    is_filed: bool
    is_overdue: bool
    notes: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class OpposingCounselCreate(BaseModel):
    case_id: int
    advocate_name: str
    bar_registration_number: Optional[str] = None
    firm_name: Optional[str] = None
    contact: Optional[str] = None


class OpposingCounselUpdate(BaseModel):
    advocate_name: Optional[str] = None
    bar_registration_number: Optional[str] = None
    firm_name: Optional[str] = None
    contact: Optional[str] = None


class OpposingCounselOut(BaseModel):
    id: int
    case_id: int
    advocate_name: str
    bar_registration_number: Optional[str]
    firm_name: Optional[str]
    contact: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}
