from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    code: str
    name: str
    price_monthly_inr: Optional[int]
    price_annual_inr: Optional[int]
    billing: str
    per_seat: bool
    min_seats: Optional[int]
    trial_days: int
    limits: dict[str, Any]
    model_config = {"from_attributes": True}


class PricingOut(BaseModel):
    """Everything the public pricing page needs — all of it data, none of it hard-coded."""
    plans: list[PlanOut]
    founding_member: dict[str, Any]
    trial: dict[str, Any]
    gst: dict[str, Any]
    billing_mode: str


class SubscriptionOut(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    billing_cycle: str
    seats: int
    current_period_start: datetime
    current_period_end: datetime
    trial_end: Optional[datetime]
    cancel_at_period_end: bool
    founding_member: bool
    gstin: Optional[str]


class UsageItem(BaseModel):
    used: int
    limit: Optional[int]        # None = unlimited / custom
    remaining: Optional[int]


class UsageOut(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    seats: int
    period_start: datetime
    period_end: datetime
    items: dict[str, UsageItem]


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=40)
    billing_cycle: str = Field(default="monthly", pattern=r"^(monthly|annual)$")
    seats: int = Field(default=1, ge=1, le=500)
    gstin: Optional[str] = Field(default=None, max_length=20)


class CheckoutOut(BaseModel):
    """Razorpay checkout handoff. We never see card data — Razorpay collects it."""
    provider: str
    mode: str                      # test | live
    key_id: Optional[str]
    order_id: Optional[str]
    amount_paise: int
    gst_paise: int
    total_paise: int
    currency: str = "INR"
    plan_code: str
    billing_cycle: str
    seats: int
    auto_renew_disclosure: str
    refund_policy: str
    cancel_anytime: bool = True


class SeatsRequest(BaseModel):
    seats: int = Field(ge=1, le=500)


class InvoiceOut(BaseModel):
    id: int
    invoice_number: str
    amount_inr: float
    gst_inr: float
    total_inr: float
    gst_rate_percent: int
    gstin: Optional[str]
    period_start: datetime
    period_end: datetime
    created_at: Optional[datetime]
