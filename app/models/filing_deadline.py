from sqlalchemy import String, Date, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class FilingDeadline(Base):
    __tablename__ = "filing_deadlines"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    deadline_date: Mapped[Date] = mapped_column(Date, nullable=False)
    is_filed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="filing_deadlines")
