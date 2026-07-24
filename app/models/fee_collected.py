import enum
from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class PaymentMode(str, enum.Enum):
    cash = "cash"
    bank_transfer = "bank_transfer"
    cheque = "cheque"
    upi = "upi"
    other = "other"


class FeeCollected(Base):
    __tablename__ = "fees_collected"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[Date] = mapped_column(Date, nullable=False)
    payment_mode: Mapped[PaymentMode] = mapped_column(Enum(PaymentMode), default=PaymentMode.cash, nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="fees_collected")
