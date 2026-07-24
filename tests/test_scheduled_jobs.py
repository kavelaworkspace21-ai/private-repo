"""Phase 3 — durable, idempotent scheduled jobs (app/services/scheduler.py).

Self-contained sqlite (no app client) so these are fast and exercise the real DB claim/record
paths. Pins: success + failure are recorded, a failing job never propagates, the same slot runs
at most once (multi-worker safety), and staleness is detected for alerting.
"""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — registers ScheduledJobRun on Base.metadata
from app.db.base import Base
from app.models.scheduled_job_run import ScheduledJobRun
from app.services import scheduler as sched
from app.util.time import utcnow


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_success_is_recorded(db):
    calls = []
    status = sched.run_tracked_job(db, "daily_reminders", "2026-07-21",
                                   lambda d: (calls.append(1), "3 reminders fired")[1])
    assert status == "success"
    row = db.query(ScheduledJobRun).one()
    assert row.status == "success" and row.finished_at is not None
    assert "3 reminders fired" in row.detail
    assert len(calls) == 1


def test_failure_is_recorded_and_never_propagates(db):
    def boom(_db):
        raise ValueError("kaboom")

    status = sched.run_tracked_job(db, "daily_backup", "2026-07-21", boom)  # must NOT raise
    assert status == "failed"
    row = db.query(ScheduledJobRun).filter_by(job_id="daily_backup").one()
    assert row.status == "failed" and "kaboom" in row.detail and row.finished_at is not None


def test_same_slot_runs_at_most_once(db):
    calls = []

    def fn(_db):
        calls.append(1)

    assert sched.run_tracked_job(db, "daily_reminders", "slot-A", fn) == "success"
    assert sched.run_tracked_job(db, "daily_reminders", "slot-A", fn) == "skipped_duplicate"
    assert len(calls) == 1
    assert db.query(ScheduledJobRun).filter_by(job_id="daily_reminders", slot_key="slot-A").count() == 1


def test_different_slots_both_run(db):
    calls = []
    sched.run_tracked_job(db, "daily_reminders", "2026-07-21", lambda d: calls.append(1))
    sched.run_tracked_job(db, "daily_reminders", "2026-07-22", lambda d: calls.append(1))
    assert len(calls) == 2


def test_staleness_detection(db):
    # a fresh success → not stale
    sched.run_tracked_job(db, "daily_reminders", "s1", lambda d: "ok")
    # an old success → stale
    old = ScheduledJobRun(job_id="daily_backup", slot_key="old", status="success", worker="x")
    db.add(old)
    db.commit()
    old.started_at = utcnow() - timedelta(days=3)
    db.commit()

    health = {h["job_id"]: h for h in sched.job_health(db)}
    assert health["daily_reminders"]["stale"] is False
    assert health["daily_backup"]["stale"] is True
    # a job that never ran is stale by definition
    assert health["weekly_corpus_freshness"]["stale"] is True
    assert set(sched.stale_jobs(db)) == {"daily_backup", "weekly_corpus_freshness"}
