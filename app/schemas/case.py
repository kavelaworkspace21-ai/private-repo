from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.case import CaseStatus


class CaseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: CaseStatus = CaseStatus.open
    client_id: int


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CaseStatus] = None
    client_id: Optional[int] = None


class CaseOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: CaseStatus
    client_id: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
