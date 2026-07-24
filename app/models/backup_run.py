from datetime import datetime
from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class BackupRun(Base):
    """
    A record of a database backup (CLAUDE.md §5 system table + §6 step 9 "backup job").
    System-level (no tenant_id): a backup covers the whole database. Rows are an auditable
    history of when backups ran, whether they succeeded, where they landed, and how big.
    """
    __tablename__ = "backup_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    engine: Mapped[str] = mapped_column(String(20), nullable=False)        # sqlite | postgresql
    status: Mapped[str] = mapped_column(String(24), nullable=False)        # success | failed | aurora_managed
    location: Mapped[str | None] = mapped_column(String(500))             # file path or note
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual | scheduled
    detail: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
