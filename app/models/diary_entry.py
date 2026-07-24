import enum
from sqlalchemy import String, Text, Date, Time, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class HearingStage(str, enum.Enum):
    first_hearing = "first_hearing"
    arguments = "arguments"
    final_arguments = "final_arguments"
    judgment = "judgment"
    other = "other"


class HearingOutcome(str, enum.Enum):
    pending = "pending"
    heard = "heard"
    adjourned = "adjourned"
    part_heard = "part_heard"
    decided = "decided"


class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    hearing_date: Mapped[Date] = mapped_column(Date, nullable=False)
    hearing_time: Mapped[Time | None] = mapped_column(Time)
    court_name: Mapped[str] = mapped_column(String(300), nullable=False)
    court_room: Mapped[str | None] = mapped_column(String(100))
    stage: Mapped[HearingStage] = mapped_column(Enum(HearingStage), default=HearingStage.other, nullable=False)
    outcome: Mapped[HearingOutcome] = mapped_column(Enum(HearingOutcome), default=HearingOutcome.pending, nullable=False)
    adjournment_reason: Mapped[str | None] = mapped_column(String(500))
    next_date: Mapped[Date | None] = mapped_column(Date)
    order_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="diary_entries")
