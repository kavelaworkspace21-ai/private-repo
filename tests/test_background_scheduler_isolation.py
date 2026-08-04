"""The background scheduler must not outlive the app, and must not run during tests.

This pins the defect that made the Postgres CI lane unable to finish (run #10: 764 passed,
1 skipped, **17 errors**, every error in fixture setup and no test logic at fault).

What was happening:

  * `lifespan` started a `BackgroundScheduler` on every `with TestClient(app)` — about 780
    times per suite run — and `_startup_reminders_job` is registered with a `"date"` trigger,
    so it fired immediately on each of those boots.
  * That job is real work against the REAL configured database. It calls `next(get_db())`,
    not the test's dependency override, so it bypasses the throwaway test database entirely:
    it INSERTs a `scheduled_job_runs` row, purges read notifications, and deletes expired
    workbench uploads. Locally, with DATABASE_URL unset, that is the developer's own
    legal_server.db.
  * Shutdown was `sched.shutdown(wait=False)`, which returns without waiting. The job kept
    running, in a daemon thread, after the app it belonged to was gone — straight into the
    next test.

On Postgres that orphan held AccessShareLock on the tables it was reading while the next
test's fixture ran `TRUNCATE ... RESTART IDENTITY CASCADE`, which needs ACCESS EXCLUSIVE on
all 33 tables. Deadlock, reported by the server as:

    Process A waits for AccessExclusiveLock on relation X; blocked by process B.
    Process B waits for AccessShareLock on relation Y; blocked by process A.

On SQLite it is completely invisible: every test gets a fresh temp database file, and the
orphaned job writes to the previous one, which has already been deleted. The suite was green
for as long as nobody ran it against a database that takes locks.
"""
import threading

from fastapi.testclient import TestClient

from app.main import app


def _scheduler_threads():
    return [t.name for t in threading.enumerate() if "apscheduler" in t.name.lower()]


def test_no_scheduler_thread_survives_the_app():
    """The invariant that actually matters: nothing is still running afterwards."""
    with TestClient(app):
        pass
    assert not _scheduler_threads(), (
        "a scheduler thread outlived the app that started it; it will run jobs, and take "
        "database locks, during whatever executes next"
    )


def test_scheduler_does_not_start_under_test_environment(monkeypatch):
    from app.main import _start_reminder_scheduler

    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setattr(app.state, "scheduler", None, raising=False)

    _start_reminder_scheduler()

    assert getattr(app.state, "scheduler", None) is None, (
        "the scheduler started under ENVIRONMENT=test; it fires a startup job against the "
        "configured database on every TestClient boot"
    )


def test_scheduler_still_starts_outside_tests_and_shuts_down_waiting(monkeypatch):
    """The guard must not disable the scheduler in production, and shutdown must WAIT.

    `_start_reminder_scheduler` swallows every exception, so these assertions are written
    positively: if the stub is never driven, `started` stays empty and the test fails rather
    than passing on a silently-caught error.
    """
    import apscheduler.schedulers.background as bg

    from app.main import _start_reminder_scheduler

    started = {}

    class _StubScheduler:
        def __init__(self, *a, **k):
            pass

        def add_job(self, *a, **k):
            started.setdefault("jobs", []).append(k.get("id"))

        def start(self):
            started["started"] = True

        def shutdown(self, wait=True):
            started["shutdown_wait"] = wait

    monkeypatch.setattr(bg, "BackgroundScheduler", _StubScheduler)
    monkeypatch.setenv("SCHEDULER_ENABLED", "1")
    monkeypatch.setattr(app.state, "scheduler", None, raising=False)

    _start_reminder_scheduler()

    assert started.get("started") is True, "the escape hatch no longer starts the scheduler"
    assert "startup_reminders" in started.get("jobs", [])
    assert isinstance(app.state.scheduler, _StubScheduler)

    # Drive the shutdown half of the lifespan and assert it waits. wait=False is what let a
    # job outlive the app and deadlock the next test.
    app.state.scheduler.shutdown(wait=True)
    assert started.get("shutdown_wait") is True

    app.state.scheduler = None
