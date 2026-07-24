from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Notification(Base):
    """
    A delivered reminder/notice. Always created in-app (the durable record + audit trail);
    email is sent additionally when SMTP is configured. `dedupe_key` makes reminder firing
    idempotent so the same hearing/deadline window is never notified twice.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)   # None = tenant-wide
    type: Mapped[str] = mapped_column(String(40), default="reminder", nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(String(1000))
    link: Mapped[str | None] = mapped_column(String(200))              # in-app target, e.g. /diary
    dedupe_key: Mapped[str | None] = mapped_column(String(200), index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
