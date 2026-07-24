from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AuditLog(Base):
    """Immutable record of every important mutation (who, what, when, tenant)."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)   # e.g. "create_case"
    entity: Mapped[str] = mapped_column(String(80), nullable=False)   # e.g. "Case"
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
