"""
Database backup job (CLAUDE.md §6 step 9 "backup job" + §5 BackupRun table).

- SQLite (local/dev): a real, consistent copy via SQLite's online-backup API (safe while the
  app is running), into BACKUP_DIR, with a rolling retention of the most recent N files.
- PostgreSQL/Aurora (production): Amazon RDS already performs automated, continuous backups
  (point-in-time recovery + daily snapshots). The app records that the backup window is
  RDS-managed; logical `pg_dump` exports are an ops/cron step on the EC2 box (see LSAI-SKILL-10).

Every run is recorded as a BackupRun row — an auditable history of when/whether backups happened.
"""
import os
import sqlite3
import glob
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.backup_run import BackupRun
from app.services.tenancy import write_audit

def _backup_dir() -> str:
    return os.getenv("BACKUP_DIR", "backups")     # read at call time (testable/overridable)


def _keep() -> int:
    return int(os.getenv("BACKUP_KEEP", "7"))      # rolling retention for file backups


def _prune(keep: int | None = None) -> int:
    """Keep only the most recent `keep` SQLite backup files; delete older ones."""
    keep = _keep() if keep is None else keep
    files = sorted(glob.glob(os.path.join(_backup_dir(), "legalserver-*.db")))
    removed = 0
    for old in files[:-keep] if keep > 0 else files:
        try:
            os.remove(old); removed += 1
        except OSError:
            pass
    return removed


def _sqlite_backup(src_path: str) -> tuple[str, int]:
    """Consistent online copy of a live SQLite DB. Returns (dest_path, size_bytes)."""
    bdir = _backup_dir()
    os.makedirs(bdir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    dst = os.path.join(bdir, f"legalserver-{ts}.db")
    src_conn = sqlite3.connect(src_path)
    dst_conn = sqlite3.connect(dst)
    try:
        with dst_conn:
            src_conn.backup(dst_conn)        # online backup API — safe under concurrent writes
    finally:
        dst_conn.close()
        src_conn.close()
    return dst, os.path.getsize(dst)


def verify_backup(path: str) -> dict:
    """Restore-drill: open a SQLite backup file and confirm it is a valid, restorable DB with the
    core schema. Returns {ok, integrity, table_count, has_core}. Proves a backup isn't silently
    corrupt — run this against the latest backup periodically (and in tests)."""
    conn = sqlite3.connect(path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        conn.close()
    has_core = {"users", "tenants"} <= tables
    return {"ok": integrity == "ok" and has_core, "integrity": integrity,
            "table_count": len(tables), "has_core": has_core}


def run_backup(db: Session, trigger: str = "manual", user=None) -> BackupRun:
    """Perform a backup of the database bound to this session and record a BackupRun."""
    bind = db.get_bind()
    url = bind.url
    driver = url.get_backend_name()          # 'sqlite' | 'postgresql'
    run = BackupRun(engine=driver, status="failed", trigger=trigger, size_bytes=0)
    db.add(run); db.flush()                   # get an id

    try:
        if driver == "sqlite":
            path = url.database
            if not path or path == ":memory:":
                run.status = "failed"
                run.detail = "in-memory SQLite has no file to back up"
            else:
                dst, size = _sqlite_backup(path)
                run.status = "success"
                run.location = dst
                run.size_bytes = size
                run.detail = f"online copy; pruned {_prune()} old file(s)"
        elif driver == "postgresql":
            run.status = "aurora_managed"
            run.location = "Amazon RDS automated backups (PITR + daily snapshots)"
            run.detail = "RDS-managed; run pg_dump from EC2/ops for logical exports (LSAI-SKILL-10)"
        else:
            run.status = "failed"
            run.detail = f"unsupported engine: {driver}"
    except Exception as e:                     # never crash the caller / scheduler
        run.status = "failed"
        run.detail = str(e)[:480]

    run.finished_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(run)

    if user is not None:                       # audit manual (admin-triggered) runs
        write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                    action="run_backup", entity="BackupRun", entity_id=run.id,
                    detail=f"{run.engine} {run.status}")
    return run
