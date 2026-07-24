import enum
from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Enum, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class FeeType(str, enum.Enum):
    retainer = "retainer"
    appearance = "appearance"
    consultation = "consultation"
    documentation = "documentation"
    misc = "misc"


class FeeDue(Base):
    __tablename__ = "fees_due"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    fee_type: Mapped[FeeType] = mapped_column(Enum(FeeType), default=FeeType.misc, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[Date] = mapped_column(Date, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="fees_due")
