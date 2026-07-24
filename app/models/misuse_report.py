from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

CATEGORIES = ("abuse", "security", "objectionable_content", "impersonation", "other")
STATUSES = ("received", "in_review", "actioned", "dismissed")


class MisuseReport(Base):
    """A user-submitted report of misuse / abuse / objectionable content (LSAI-LEGAL-16).

    Required for safe operation and app-store compliance (a clear way to report abuse). Triaged
    by firm admins; every create/update is audited and tenant-scoped."""
    __tablename__ = "misuse_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, index=True)
    reporter_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    resolver_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[DateTime | None] = mapped_column(DateTime)
