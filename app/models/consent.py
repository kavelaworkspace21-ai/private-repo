from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ConsentRecord(Base):
    """
    A recorded consent/privacy acceptance (CLAUDE.md §5; DPDP Act 2023 — consent must be
    free, specific, informed, and auditable). One row per consent type + version, with the
    timestamp and source IP so the grant is provable.
    """
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    consent_type: Mapped[str] = mapped_column(String(40), nullable=False)   # terms_of_service | privacy_policy
    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    granted: Mapped[bool] = mapped_column(default=True, nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))             # provable receipt (DPDP)
    acceptance_source: Mapped[str | None] = mapped_column(String(40))       # registration | consent_page | policy_update
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
