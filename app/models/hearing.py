import enum
from sqlalchemy import String, Text, DateTime, Date, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class HearingStatus(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    adjourned = "adjourned"
    cancelled = "cancelled"


class Hearing(Base):
    __tablename__ = "hearings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    hearing_date: Mapped[Date] = mapped_column(Date, nullable=False)
    court_name: Mapped[str] = mapped_column(String(300), nullable=False)
    judge_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[HearingStatus] = mapped_column(Enum(HearingStatus), default=HearingStatus.scheduled, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    next_hearing_date: Mapped[Date | None] = mapped_column(Date)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="hearings")
