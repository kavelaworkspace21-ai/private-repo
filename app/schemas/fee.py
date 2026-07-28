from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from app.models.fee_collected import PaymentMode
from app.models.fee_due import FeeType

# Fee amounts had NO bounds: negative, zero and absurd values were all accepted and stored.
# These are the advocate's OWN ledger entries (what they bill their clients), not payments to
# Juriscite, so this is a data-INTEGRITY flaw rather than a way to extract money from the
# platform. It still matters: a negative receipt silently corrupts outstanding-balance and
# revenue totals, and a compromised account — or a malicious clerk inside the firm — could
# quietly wreck the books. The ceiling is ~1 billion, comfortably above any real Indian legal
# fee while blocking float values large enough to lose precision.
#
# NOTE: money is stored as float here. That is a pre-existing correctness concern (0.1 + 0.2
# problems on totals) and changing it is a schema migration, tracked in OWNER_QUEUE.
Money = Field(ge=0, le=1_000_000_000)
OptionalMoney = Field(default=None, ge=0, le=1_000_000_000)


class FeeCollectedCreate(BaseModel):
    case_id: int
    amount: float = Money
    payment_date: date
    payment_mode: PaymentMode = PaymentMode.cash
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class FeeCollectedUpdate(BaseModel):
    amount: Optional[float] = OptionalMoney
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
    amount: float = Money
    due_date: date
    description: Optional[str] = None


class FeeDueUpdate(BaseModel):
    fee_type: Optional[FeeType] = None
    amount: Optional[float] = OptionalMoney
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
