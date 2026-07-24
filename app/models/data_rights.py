from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

REQUEST_TYPES = ("access", "export", "correction", "erasure", "grievance", "withdrawal")
STATUSES = ("received", "in_review", "completed", "rejected")


class DataRightsRequest(Base):
    """A DPDP data-principal rights request (access/export/correction/erasure/grievance/withdrawal),
    tracked with a status + statutory deadline so the obligation is provable (LSAI-LEGAL-05)."""
    __tablename__ = "data_rights_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    request_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    resolver_note: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[DateTime | None] = mapped_column(DateTime)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[DateTime | None] = mapped_column(DateTime)
