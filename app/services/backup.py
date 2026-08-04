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
import tarfile
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


# ── Uploaded files ─────────────────────────────────────────────────────────────
# The database backup does NOT cover the documents.
#
# Document ROWS are in the database. Document BYTES are on local disk under
# data/uploads/<tenant_id>/ (app/services/storage.py is filesystem-only). On PostgreSQL this
# module used to do nothing at all — RDS covers the relational half, and nothing covered the
# files. Restore the database alone and every document row points at a file that is not there:
# read_file() returns None, the UI still lists the document, and the bytes are gone. Nothing in
# the database is wrong, so no database-level check can see it.
#
# So the uploads tree is archived on EVERY run, on BOTH engines.
#
# NOTE ON WHAT THIS DOES AND DOES NOT ACHIEVE. Writing the archive into BACKUP_DIR puts it on
# the same disk as the thing it protects, which is not durability. What it buys is that the
# files become ONE artifact to ship off-box, and that the app's own backup record stops
# implying the files are covered when they are not. Real durability needs BACKUP_DIR (or
# UPLOADS_BACKUP_DIR) pointed at mounted durable storage, or the S3 swap storage.py was
# designed for. The production boot gate in app/security_gate.py refuses to start until the
# operator has said which.

def _uploads_dir() -> str:
    """The directory storage.py actually writes to — asked at call time, never re-derived.

    storage.UPLOAD_DIR is an ABSOLUTE path (ROOT / "data" / "uploads"). An independent default
    of "data/uploads" here would resolve against the current working directory instead, so the
    two would agree only when the app happened to be started from the repo root — and when
    they disagreed the backup would archive an empty or non-existent directory and report
    success. Importing the constant makes that class of bug impossible; reading it through the
    module (rather than `from ... import UPLOAD_DIR`) keeps it monkeypatchable in tests.
    """
    from app.services import storage
    return str(storage.UPLOAD_DIR)


def _uploads_backup_dir() -> str:
    """Where upload archives are written. Defaults to BACKUP_DIR, overridable so the archive
    can be sent somewhere durable without moving the database backups too."""
    return os.getenv("UPLOADS_BACKUP_DIR", _backup_dir())


def _prune_uploads(keep: int | None = None) -> int:
    keep = _keep() if keep is None else keep
    files = sorted(glob.glob(os.path.join(_uploads_backup_dir(), "uploads-*.tar.gz")))
    removed = 0
    for old in files[:-keep] if keep > 0 else files:
        try:
            os.remove(old); removed += 1
        except OSError:
            pass
    return removed


def backup_uploads() -> dict:
    """Archive the uploads tree. Returns {path, size_bytes, file_count, pruned, skipped}.

    An absent or empty uploads directory is a successful no-op, not a failure — a fresh
    install legitimately has no files, and failing there would train whoever reads these rows
    to ignore a failed backup.
    """
    src = _uploads_dir()
    bdir = _uploads_backup_dir()
    os.makedirs(bdir, exist_ok=True)

    if not os.path.isdir(src):
        return {"path": None, "size_bytes": 0, "file_count": 0, "pruned": 0,
                "skipped": "no uploads directory"}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    dst = os.path.join(bdir, f"uploads-{ts}.tar.gz")

    count = 0
    # Write to a temp name and rename on success, so a crash mid-archive cannot leave a
    # truncated file that looks like a complete backup.
    tmp = dst + ".partial"
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            for root, _dirs, files in os.walk(src):
                for name in files:
                    full = os.path.join(root, name)
                    # Never follow a symlink out of the tree into the wider filesystem.
                    if os.path.islink(full):
                        continue
                    tar.add(full, arcname=os.path.relpath(full, src))
                    count += 1
        os.replace(tmp, dst)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

    return {"path": dst, "size_bytes": os.path.getsize(dst), "file_count": count,
            "pruned": _prune_uploads(), "skipped": None}


def verify_uploads_backup(path: str) -> dict:
    """Open an upload archive and confirm it is readable and non-truncated.

    The same argument as verify_backup() for the database: an archive nobody has opened is
    not known to be an archive. Returns {ok, file_count, error}.
    """
    try:
        with tarfile.open(path, "r:gz") as tar:
            names = [m.name for m in tar.getmembers() if m.isfile()]
        return {"ok": True, "file_count": len(names), "error": None}
    except Exception as exc:
        return {"ok": False, "file_count": 0, "error": f"{type(exc).__name__}: {exc}"}


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

        # Uploaded files, on BOTH engines. RDS covers the relational half and nothing covered
        # this half, which is the whole point of doing it here rather than in the sqlite branch.
        # A failure here fails the RUN — a backup that silently omits the client's documents is
        # the kind of green result this project keeps finding and regretting.
        if run.status in ("success", "aurora_managed"):
            up = backup_uploads()
            if up["skipped"]:
                run.detail = f"{run.detail or ''} | uploads: {up['skipped']}".strip(" |")
            else:
                run.size_bytes = (run.size_bytes or 0) + up["size_bytes"]
                run.detail = (f"{run.detail or ''} | uploads: {up['file_count']} file(s), "
                              f"{up['size_bytes']} bytes -> {up['path']}"
                              f"{f', pruned {up['pruned']}' if up['pruned'] else ''}").strip(" |")
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
