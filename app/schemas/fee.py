from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from app.models.fee_collected import PaymentMode
from app.models.fee_due import FeeType


class FeeCollectedCreate(BaseModel):
    case_id: int
    amount: float
    payment_date: date
    payment_mode: PaymentMode = PaymentMode.cash
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class FeeCollectedUpdate(BaseModel):
    amount: Optional[float] = None
    payment_date: Optional[date] = None
    payment_mode: Optional[PaymentMode] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class FeeCollectedOut(BaseModel):
    id: int
    case_id: int
    amount: float
    payment_date: date
    payment_mode: PaymentMode
    reference_number: Optional[str]
    notes: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class FeeDueCreate(BaseModel):
    case_id: int
    fee_type: FeeType = FeeType.misc
    amount: float
    due_date: date
    description: Optional[str] = None


class FeeDueUpdate(BaseModel):
    fee_type: Optional[FeeType] = None
    amount: Optional[float] = None
    due_date: Optional[date] = None
    is_paid: Optional[bool] = None
    description: Optional[str] = None


class FeeDueOut(BaseModel):
    id: int
    case_id: int
    fee_type: FeeType
    amount: float
    due_date: date
    is_paid: bool
    description: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}
