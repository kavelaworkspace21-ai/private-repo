from sqlalchemy import String, Text, Date, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class DiaryTask(Base):
    __tablename__ = "diary_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[Date | None] = mapped_column(Date)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="diary_tasks")
