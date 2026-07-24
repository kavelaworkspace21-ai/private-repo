from datetime import datetime

from sqlalchemy import String, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScheduledJobRun(Base):
    """Durable record of a scheduled-job execution (Phase 3). System-level (no tenant_id):
    reminders, backups, and the weekly drift check cover the whole instance.

    The ``UNIQUE(job_id, slot_key)`` constraint is the idempotency guard: the first worker to
    claim a (job, time-slot) inserts its row; any other worker/instance firing the same job for
    the same slot hits the constraint and SKIPS. So a job runs at most once per slot even under
    multiple Uvicorn workers — without needing Redis. Rows are also an auditable history of when
    each job ran, whether it succeeded, and why it failed.
    """
    __tablename__ = "scheduled_job_runs"
    __table_args__ = (UniqueConstraint("job_id", "slot_key", name="uq_job_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    slot_key: Mapped[str] = mapped_column(String(64), nullable=False)   # daily date / week / boot id
    status: Mapped[str] = mapped_column(String(16), nullable=False)     # running | success | failed
    detail: Mapped[str | None] = mapped_column(String(1000))
    worker: Mapped[str | None] = mapped_column(String(80))              # host:pid that claimed it
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
