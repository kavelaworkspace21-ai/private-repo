from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from app.models.hearing import HearingStatus


class HearingCreate(BaseModel):
    case_id: int
    hearing_date: date
    court_name: str
    judge_name: Optional[str] = None
    status: HearingStatus = HearingStatus.scheduled
    notes: Optional[str] = None
    next_hearing_date: Optional[date] = None


class HearingUpdate(BaseModel):
    hearing_date: Optional[date] = None
    court_name: Optional[str] = None
    judge_name: Optional[str] = None
    status: Optional[HearingStatus] = None
    notes: Optional[str] = None
    next_hearing_date: Optional[date] = None


class HearingOut(BaseModel):
    id: int
    case_id: int
    hearing_date: date
    court_name: str
    judge_name: Optional[str]
    status: HearingStatus
    notes: Optional[str]
    next_hearing_date: Optional[date]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}
