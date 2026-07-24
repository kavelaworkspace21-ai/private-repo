"""Durable, idempotent scheduled-job execution (Phase 3).

APScheduler runs IN-PROCESS. Under a single Uvicorn worker (the current EC2/systemd topology)
each job fires once. If the deployment ever runs multiple workers/instances, each process has
its own scheduler and would fire the same job — so ``run_tracked_job()`` claims a
``(job_id, slot_key)`` row under a UNIQUE constraint and SKIPS if another worker already claimed
it (exactly-once per slot, no Redis needed). Every run is persisted (start/end/status/detail)
for audit and staleness alerting.
"""
import logging
import os
import socket
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.scheduled_job_run import ScheduledJobRun
from app.util.time import utcnow

logger = logging.getLogger(__name__)

# Max age since the last SUCCESS before a job is considered stale (missed). Margins are generous
# so a single slow/late run doesn't false-alarm.
JOB_MAX_AGE = {
    "daily_reminders": timedelta(hours=26),
    "daily_backup": timedelta(hours=26),
    "weekly_corpus_freshness": timedelta(days=8),
}


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def run_tracked_job(db, job_id: str, slot_key: str, fn) -> str:
    """Run ``fn(db)`` at most once per ``(job_id, slot_key)``, recording the outcome.

    Returns ``"success"``, ``"failed"``, or ``"skipped_duplicate"``. Never raises out: a failing
    scheduled job is recorded + logged (for alerting), not allowed to crash the scheduler thread.
    """
    run = ScheduledJobRun(job_id=job_id, slot_key=slot_key, status="running", worker=worker_id())
    db.add(run)
    try:
        db.commit()                       # claim the slot — UNIQUE(job_id, slot_key)
    except IntegrityError:
        db.rollback()
        logger.info(f"Scheduled job {job_id} slot {slot_key} already claimed — skipping duplicate.")
        return "skipped_duplicate"

    try:
        detail = fn(db)
        run.status = "success"
        run.detail = str(detail)[:1000] if detail is not None else None
    except Exception as e:
        db.rollback()                     # undo any partial work from the failed job
        run.status = "failed"
        run.detail = f"{type(e).__name__}: {e}"[:1000]
        logger.error(f"Scheduled job {job_id} (slot {slot_key}) FAILED: {run.detail}")
    finally:
        run.finished_at = utcnow()
        db.add(run)
        db.commit()
    return run.status


def job_health(db) -> list[dict]:
    """Per-known-job: last success, last status, and whether it's stale (missed). Feeds a status
    endpoint / alerting. A job with no successful run ever is stale by definition."""
    now = utcnow()
    out: list[dict] = []
    for job_id, max_age in JOB_MAX_AGE.items():
        last_success = db.execute(
            select(ScheduledJobRun)
            .where(ScheduledJobRun.job_id == job_id, ScheduledJobRun.status == "success")
            .order_by(ScheduledJobRun.started_at.desc())
        ).scalars().first()
        last_any = db.execute(
            select(ScheduledJobRun)
            .where(ScheduledJobRun.job_id == job_id)
            .order_by(ScheduledJobRun.started_at.desc())
        ).scalars().first()
        stale = last_success is None or (now - last_success.started_at) > max_age
        out.append({
            "job_id": job_id,
            "last_success_at": last_success.started_at.isoformat() if last_success else None,
            "last_status": last_any.status if last_any else None,
            "stale": stale,
        })
    return out


def stale_jobs(db) -> list[str]:
    """Job ids whose last success is older than their max age (or never succeeded)."""
    return [h["job_id"] for h in job_health(db) if h["stale"]]
