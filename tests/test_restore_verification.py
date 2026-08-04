"""The restore verifier must actually detect a bad restore.

`scripts/verify_restore.py` exists to answer one question: *did this restore bring everything
back?* Its most important check walks the filesystem, because document BYTES live on local
disk under `data/uploads/` while document ROWS live in PostgreSQL — so a database-only restore
leaves every document row pointing at a file that is not there, and nothing in the database is
wrong. No database-level check can see it.

A verifier that cannot fail is worse than none, since it reads as assurance. These tests drive
it against a deliberately incomplete restore and assert it says so.

This is also a regression guard for a real defect the script had on its first run: it looked
for `document_versions.file_path`, but that table spells the column `storage_path` (only
`documents` uses `file_path`). The hash check SKIPPED silently rather than failing — exactly
the shape of a check that reports nothing.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import app.models  # noqa: F401  registers every model on Base.metadata
from app.db.base import Base

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_verifier():
    """Import scripts/verify_restore.py by path — `scripts/` is not a package."""
    path = REPO_ROOT / "scripts" / "verify_restore.py"
    spec = importlib.util.spec_from_file_location("verify_restore", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_restore"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def restored(tmp_path):
    """A 'restored' database plus a file root, seeded with one matter and two documents.

    Built with create_all and a stamped alembic_version rather than by running the migration
    chain: this test is about the VERIFIER, and paying ~20s of subprocess migrations to get a
    schema that create_all produces instantly would be cost without cover. The chain itself is
    tested in tests/test_migration_on_populated_db.py.
    """
    db_path = tmp_path / "restored.db"
    files_root = tmp_path / "srv"
    (files_root / "data" / "uploads" / "1").mkdir(parents=True)

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)

    release = __import__("json").loads((REPO_ROOT / "RELEASE.json").read_text(encoding="utf-8"))
    T = Base.metadata.tables
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32))"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                     {"v": release["migration_head"]})

        tid = conn.execute(T["tenants"].insert().returning(T["tenants"].c.id),
                           {"name": "Firm One"}).scalar()
        cid = conn.execute(T["clients"].insert().returning(T["clients"].c.id),
                           {"tenant_id": tid, "full_name": "A Client",
                            "email": "a@client.test"}).scalar()
        case_id = conn.execute(T["cases"].insert().returning(T["cases"].c.id),
                               {"tenant_id": tid, "title": "A Matter", "status": "open",
                                "client_id": cid}).scalar()

        present = files_root / "data/uploads/1/present.pdf"
        present.write_bytes(b"%PDF-1.4 these bytes were restored")
        for name in ("present.pdf", "lost.pdf"):
            conn.execute(T["documents"].insert(), {
                "tenant_id": tid, "case_id": case_id, "filename": name,
                "file_path": f"data/uploads/1/{name}"})

    engine.dispose()
    return {"url": f"sqlite:///{db_path.as_posix()}", "files_root": files_root,
            "present": present}


def _run(verifier, restored, extra=()):
    argv = ["verify_restore.py", "--database-url", restored["url"],
            "--files-root", str(restored["files_root"]), *extra]
    return verifier.main(argv)


def test_detects_a_database_only_restore(restored, capsys):
    """The headline case: rows restored, files not. Must FAIL."""
    verifier = _load_verifier()
    code = _run(verifier, restored)
    out = capsys.readouterr().out

    assert code == 1, "a restore missing its document files was reported as successful"
    assert "documents have their files" in out
    assert "DO NOT EXIST" in out
    assert "lost.pdf" in out, "the failure did not name the missing file"


def test_passes_when_the_files_are_restored_too(restored, capsys):
    """...and it must PASS once the file storage is restored as well.

    Without this, the previous test would also pass if the verifier simply always failed.
    """
    verifier = _load_verifier()
    (restored["files_root"] / "data/uploads/1/lost.pdf").write_bytes(b"%PDF recovered")

    code = _run(verifier, restored)
    out = capsys.readouterr().out
    assert code == 0, f"a complete restore was reported as failed:\n{out}"
    assert "Restore verification passed" in out


def test_detects_a_corrupted_file_not_merely_a_missing_one(restored, capsys):
    """A file that is present but whose bytes changed must fail the hash check.

    Guards the `storage_path` vs `file_path` defect: if the verifier cannot read
    document_versions it must FAIL, never skip quietly.
    """
    verifier = _load_verifier()
    (restored["files_root"] / "data/uploads/1/lost.pdf").write_bytes(b"%PDF recovered")

    engine = create_engine(restored["url"])
    dv = Base.metadata.tables["document_versions"]
    with engine.begin() as conn:
        conn.execute(dv.insert(), {
            "tenant_id": 1, "document_id": 1, "version_no": 1,
            "original_filename": "present.pdf",
            "storage_path": "data/uploads/1/present.pdf",
            "size_bytes": 10, "uploaded_by": 1,
            "sha256": hashlib.sha256(b"what the file used to contain").hexdigest(),
        })
    engine.dispose()

    code = _run(verifier, restored)
    out = capsys.readouterr().out
    assert code == 1, "a file whose bytes no longer match its recorded sha256 passed"
    assert "document version hashes" in out
    assert "corruption" in out.lower()


def test_the_write_test_leaves_nothing_behind(restored, capsys):
    """The verifier writes to prove the database is writable — and must roll it back.

    A verification tool that seeds rows into the database it was validating is a
    data-integrity problem wearing a hard hat.
    """
    verifier = _load_verifier()
    (restored["files_root"] / "data/uploads/1/lost.pdf").write_bytes(b"%PDF recovered")
    _run(verifier, restored)

    engine = create_engine(restored["url"])
    with engine.connect() as conn:
        left = conn.execute(text(
            "SELECT COUNT(*) FROM tenants WHERE name = 'restore-verification-probe'"
        )).scalar()
    engine.dispose()
    assert left == 0, "the verifier's write probe was committed to the restored database"
