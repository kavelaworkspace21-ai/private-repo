from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Tenant(Base):
    """A firm / workspace. All business data is isolated by tenant_id."""
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    # Advocate/firm verification (LSAI-LEGAL-07): founder-approved for the closed beta.
    verification_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(80))          # state/bar jurisdiction
    bar_enrolment: Mapped[str | None] = mapped_column(String(80))         # firm-level enrolment ref
    verification_note: Mapped[str | None] = mapped_column(String(400))
    verified_at: Mapped[DateTime | None] = mapped_column(DateTime)
