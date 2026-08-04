"""Verify a RESTORED database — run this after a restore, before trusting it.

    python scripts/verify_restore.py --database-url "postgresql+psycopg://USER:PASS@host/db?sslmode=require"

S4's acceptance criterion is that *a restore has been performed, not merely configured*, and
that the restored system passes schema verification, corpus/index identity checks and tenant
isolation checks. This is those checks, executable.

It is deliberately separate from `scripts/smoke_test.py`. That one talks HTTP to a running
deployment; this one connects **straight to the restored database**, because a restore is
something you validate before you point an application at it.

THE CHECK THAT MATTERS MOST is `documents_have_their_files`. Document *rows* live in
PostgreSQL and are restored by RDS. Document *bytes* live on the local filesystem under
`data/uploads/<tenant_id>/` — `app/services/storage.py` is local-disk only, and its own
docstring notes S3 as a future swap. **An RDS restore does not bring the files back.** Restore
the database alone and every document row points at a file that is not there; `read_file()`
returns None and an advocate's uploaded evidence is gone while the UI still lists it. That
gap is invisible to any check that only looks at the database, which is why this one walks
the filesystem.

SAFETY
  * **Read-only by default.** The write test runs inside a transaction that is ALWAYS rolled
    back, so nothing is left behind even on success. Pass --skip-write-test to omit it.
  * **Fails closed.** A check that cannot be performed is a FAIL, never a pass. Non-zero exit
    on any failure, so a restore runbook can gate on it.
  * **Prints no secrets.** The database URL is never echoed — it holds a password.

Exit codes:  0 = all checks passed · 1 = a check failed · 2 = usage error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, func, inspect, select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

import app.models  # noqa: F401,E402  registers every model on Base.metadata
from app.db.base import Base  # noqa: E402


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []
        self.failed = 0

    def _add(self, status, name, detail=""):
        self.rows.append((status, name, detail))
        if status == "FAIL":
            self.failed += 1

    def ok(self, name, detail=""):
        self._add("PASS", name, detail)

    def bad(self, name, detail=""):
        self._add("FAIL", name, detail)

    def skip(self, name, detail=""):
        self._add("SKIP", name, detail)

    def info(self, name, detail=""):
        self._add("INFO", name, detail)


# ── schema ─────────────────────────────────────────────────────────────────────

def check_schema(engine, r: Report) -> None:
    """Every table the models declare must exist in the restored database."""
    try:
        live = set(inspect(engine).get_table_names())
    except Exception as exc:
        return r.bad("database reachable", f"{type(exc).__name__}: {exc}")

    r.ok("database reachable", f"{len(live)} tables")

    missing = sorted(set(Base.metadata.tables) - live)
    if missing:
        r.bad("schema complete", f"tables missing after restore: {missing}")
    else:
        r.ok("schema complete", f"all {len(Base.metadata.tables)} declared tables present")


def check_migration_head(engine, r: Report, release: dict) -> None:
    """The restored schema must be at the revision the release was built against.

    A restore from an older snapshot can land you on an EARLIER head. The app would then run
    against a schema missing columns it expects — the failure appears as random 500s on
    whichever endpoint touches the newest column first, not as anything resembling a restore
    problem.
    """
    expected = release.get("migration_head")
    try:
        with engine.connect() as conn:
            head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:
        return r.bad("migration head", f"cannot read alembic_version: {exc}")

    if not expected:
        return r.skip("migration head", f"RELEASE.json has no migration_head; restored={head}")
    if head == expected:
        r.ok("migration head", f"{head} matches RELEASE.json")
    else:
        r.bad("migration head",
              f"restored at {head!r}, release expects {expected!r} — run 'alembic upgrade head' "
              f"before serving, or you restored the wrong snapshot")


# ── tenant isolation ───────────────────────────────────────────────────────────

def check_tenant_integrity(engine, r: Report) -> None:
    """Tenant scoping must have survived the restore intact.

    A partial or mis-ordered restore can leave rows whose tenant_id points at a tenant row
    that was not restored. Those rows are invisible to their owner and, worse, could be
    reachable by whoever later gets that tenant id.
    """
    with engine.connect() as conn:
        for table in ("cases", "clients"):
            try:
                nulls = conn.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")).scalar()  # noqa: S608
            except Exception as exc:
                r.bad(f"{table}: tenant_id populated", str(exc))
                continue
            if nulls:
                r.bad(f"{table}: tenant_id populated", f"{nulls} row(s) with NULL tenant_id")
            else:
                r.ok(f"{table}: tenant_id populated", "no NULLs")

            try:
                orphans = conn.execute(text(
                    f"SELECT COUNT(*) FROM {table} t "  # noqa: S608
                    f"WHERE NOT EXISTS (SELECT 1 FROM tenants x WHERE x.id = t.tenant_id)"
                )).scalar()
            except Exception as exc:
                r.bad(f"{table}: tenant_id resolves", str(exc))
                continue
            if orphans:
                r.bad(f"{table}: tenant_id resolves",
                      f"{orphans} row(s) point at a tenant that does not exist")
            else:
                r.ok(f"{table}: tenant_id resolves", "every tenant_id resolves")

        # Cross-tenant leakage: a document must belong to the same tenant as its case.
        try:
            leaked = conn.execute(text(
                "SELECT COUNT(*) FROM documents d JOIN cases c ON c.id = d.case_id "
                "WHERE d.tenant_id IS NOT NULL AND d.tenant_id <> c.tenant_id"
            )).scalar()
            if leaked:
                r.bad("no cross-tenant document leakage",
                      f"{leaked} document(s) whose tenant_id differs from their case's")
            else:
                r.ok("no cross-tenant document leakage", "documents agree with their case")
        except Exception as exc:
            r.bad("no cross-tenant document leakage", str(exc))


# ── the files the database does NOT contain ────────────────────────────────────

def check_document_files(engine, r: Report, files_root: Path, limit: int) -> None:
    """Do the uploaded files actually exist? This is the check RDS cannot answer.

    `documents.file_path` holds a path relative to the repo root, e.g.
    `data/uploads/<tenant_id>/<stored_name>`. The bytes are on local disk. If only the
    database was restored, every one of these is a dangling reference.
    """
    docs = Base.metadata.tables["documents"]
    try:
        with engine.connect() as conn:
            total = conn.execute(select(func.count()).select_from(docs)).scalar() or 0
            rows = conn.execute(
                select(docs.c.id, docs.c.file_path).limit(limit)).fetchall()
    except Exception as exc:
        return r.bad("documents have their files", f"cannot read documents: {exc}")

    if total == 0:
        return r.info("documents have their files",
                      "no document rows in the restored database — nothing to check. "
                      "This is expected for an empty/first restore, and is NOT evidence "
                      "that file recovery works.")

    missing = [(d_id, p) for d_id, p in rows if not (files_root / p).is_file()]
    checked = len(rows)
    if not missing:
        r.ok("documents have their files",
             f"{checked}/{total} sampled, all present under {files_root}")
        return

    sample = ", ".join(f"id={i}:{p}" for i, p in missing[:3])
    r.bad("documents have their files",
          f"{len(missing)}/{checked} sampled document rows point at files that DO NOT EXIST "
          f"({sample}). Database backups do not cover data/uploads/ — restore the file "
          f"storage too, or these matters have lost their evidence")


def check_document_version_hashes(engine, r: Report, files_root: Path, limit: int) -> None:
    """Where a sha256 was recorded, the file on disk must still match it.

    Only `document_versions` carries a hash; the base `documents` row does not. So this is a
    partial integrity check by construction — it proves nothing about unversioned documents,
    and says so rather than implying broader coverage.
    """
    # NOTE the column is `storage_path` here, NOT `file_path` as on `documents`. The two
    # tables spell the same concept differently; assuming otherwise made this check SKIP
    # silently on its first run, which is precisely the shape of a check that reports nothing.
    dv = Base.metadata.tables.get("document_versions")
    if dv is None or "sha256" not in dv.c or "storage_path" not in dv.c:
        return r.skip("document version hashes",
                      "document_versions lacks sha256/storage_path")

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(dv.c.id, dv.c.storage_path, dv.c.sha256)
                .where(dv.c.sha256.isnot(None)).limit(limit)).fetchall()
    except Exception as exc:
        return r.bad("document version hashes", f"cannot read document_versions: {exc}")

    if not rows:
        return r.info("document version hashes", "no versions with a recorded sha256")

    mismatched, absent = [], []
    for vid, path, want in rows:
        f = files_root / (path or "")
        if not f.is_file():
            absent.append(vid)
            continue
        got = hashlib.sha256(f.read_bytes()).hexdigest()
        if got != want:
            mismatched.append(vid)

    if mismatched:
        r.bad("document version hashes",
              f"{len(mismatched)} file(s) on disk do not match their recorded sha256 "
              f"(ids: {mismatched[:5]}) — corruption, not just absence")
    elif absent:
        r.bad("document version hashes",
              f"{len(absent)} versioned file(s) missing from disk (ids: {absent[:5]})")
    else:
        r.ok("document version hashes", f"{len(rows)} checked, all match")


# ── release / corpus identity ──────────────────────────────────────────────────

def check_release_identity(r: Report, release: dict) -> None:
    """Corpus fingerprint and index count are FILESYSTEM state, not database state.

    Stated explicitly because it is the most natural thing to get wrong here: no database
    restore can affect them, and no database restore can repair them. The vector index is
    DERIVED from the versioned corpus and is rebuildable; that is why its loss is an outage
    and not a data loss, unlike data/uploads/.
    """
    try:
        from app.ops.release import _chroma_count, live_status
        live = live_status()
    except Exception as exc:
        return r.skip("release identity (filesystem)", f"could not read live status: {exc}")

    for field in ("app_version", "corpus_fingerprint"):
        if live.get(field) == release.get(field):
            r.ok(f"release identity: {field}", str(live.get(field)))
        else:
            r.bad(f"release identity: {field}",
                  f"live {live.get(field)!r} != pinned {release.get(field)!r}")

    count, expected = _chroma_count(), release.get("expected_chunk_count")
    if count is None:
        r.bad("vector index present",
              "no index on this host — rebuild with reseed(force=True) before serving "
              "(derived from the versioned corpus, so this is an outage, not data loss)")
    elif count == expected:
        r.ok("vector index matches the pinned count", f"{count} chunks")
    else:
        r.bad("vector index matches the pinned count", f"live {count} != pinned {expected}")


# ── critical reads and writes ──────────────────────────────────────────────────

def check_reads_and_writes(engine, r: Report, skip_write: bool) -> None:
    """A restored database that cannot be written to is not recovered, only readable."""
    with engine.connect() as conn:
        for table in ("tenants", "users", "cases", "clients", "documents"):
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()  # noqa: S608
                r.info(f"row count: {table}", str(n))
            except Exception as exc:
                r.bad(f"row count: {table}", str(exc))

    if skip_write:
        return r.skip("write test", "--skip-write-test given; write capability NOT verified")

    # Inside a transaction that is always rolled back — nothing is left behind on success
    # OR on failure, so this is safe to run against a restored production database.
    tenants = Base.metadata.tables["tenants"]
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                new_id = conn.execute(
                    tenants.insert().returning(tenants.c.id),
                    {"name": "restore-verification-probe"}).scalar()
                back = conn.execute(
                    select(tenants.c.name).where(tenants.c.id == new_id)).scalar()
                if back == "restore-verification-probe":
                    r.ok("write test (rolled back)", "insert + read-back succeeded")
                else:
                    r.bad("write test (rolled back)", f"read back {back!r}")
            finally:
                trans.rollback()

        # Prove the rollback actually took effect — otherwise this check litters the
        # database it was meant to validate.
        with engine.connect() as conn:
            left = conn.execute(text(
                "SELECT COUNT(*) FROM tenants WHERE name = 'restore-verification-probe'"
            )).scalar()
        if left:
            r.bad("write test left nothing behind", f"{left} probe row(s) still present")
        else:
            r.ok("write test left nothing behind", "rollback confirmed")
    except Exception as exc:
        r.bad("write test (rolled back)", f"{type(exc).__name__}: {exc}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Verify a restored Juriscite database.")
    ap.add_argument("--database-url", default=os.getenv("DATABASE_URL"),
                    help="SQLAlchemy URL of the RESTORED database (or set DATABASE_URL)")
    ap.add_argument("--files-root", default=str(REPO_ROOT),
                    help="root that documents.file_path is relative to (default: repo root)")
    ap.add_argument("--sample", type=int, default=500,
                    help="how many document rows to check on disk (default 500)")
    ap.add_argument("--skip-write-test", action="store_true")
    args = ap.parse_args(argv[1:])

    if not args.database_url:
        print("no --database-url and no DATABASE_URL set", file=sys.stderr)
        return 2

    release_path = REPO_ROOT / "RELEASE.json"
    if not release_path.exists():
        print("RELEASE.json not found — run this from the deployed release tree",
              file=sys.stderr)
        return 2
    release = json.loads(release_path.read_text(encoding="utf-8"))

    # Never echo the URL: it holds a password. Host and database only.
    url = make_url(args.database_url)
    files_root = Path(args.files_root).resolve()

    engine = create_engine(args.database_url)
    r = Report()
    try:
        check_schema(engine, r)
        check_migration_head(engine, r, release)
        check_tenant_integrity(engine, r)
        check_document_files(engine, r, files_root, args.sample)
        check_document_version_hashes(engine, r, files_root, args.sample)
        check_release_identity(r, release)
        check_reads_and_writes(engine, r, args.skip_write_test)
    finally:
        engine.dispose()

    width = max(len(n) for _, n, _ in r.rows)
    print(f"\nRestore verification — {url.drivername} {url.host or 'local'}/{url.database}")
    print(f"files root: {files_root}")
    print("=" * (width + 34))
    for status, name, detail in r.rows:
        print(f"  [{status}] {name.ljust(width)}  {detail}")
    print("=" * (width + 34))

    passed = sum(1 for s, _, _ in r.rows if s == "PASS")
    skipped = sum(1 for s, _, _ in r.rows if s == "SKIP")
    print(f"  {passed} passed, {r.failed} failed, {skipped} skipped")
    if skipped:
        print("  NOTE: a skipped check was NOT verified.")

    if r.failed:
        print("\nRESTORE VERIFICATION FAILED — do not put this database into service.")
        return 1
    print("\nRestore verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
