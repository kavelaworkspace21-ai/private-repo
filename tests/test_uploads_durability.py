"""Uploaded client files must be backed up, and production must refuse to pretend otherwise.

The gap this closes: document ROWS live in the database and are covered by its backups;
document BYTES live on local disk under data/uploads/ and were covered by nothing. On
PostgreSQL `run_backup()` did literally nothing — it recorded `aurora_managed` and returned,
because RDS owns the relational half. Restore the database alone and every document row points
at a file that is not there. `read_file()` returns None, the UI still lists the document, and
the bytes are gone.

**Nothing in the database is wrong when that happens**, so no database-level check can see it.
That is why the archive runs on both engines and why the boot gate exists.
"""
import os
import tarfile

import pytest

from app.services import backup as bk


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    """A fake uploads tree plus an isolated backup directory."""
    up = tmp_path / "uploads"
    (up / "1").mkdir(parents=True)
    (up / "2").mkdir(parents=True)
    (up / "1" / "brief.pdf").write_bytes(b"%PDF-1.4 tenant one brief")
    (up / "1" / "evidence.png").write_bytes(b"\x89PNG tenant one evidence")
    (up / "2" / "contract.pdf").write_bytes(b"%PDF-1.4 tenant two contract")

    from app.services import storage
    monkeypatch.setattr(storage, "UPLOAD_DIR", up)
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("UPLOADS_BACKUP_DIR", raising=False)
    return {"root": up, "backups": tmp_path / "backups"}


# ── the archive itself ─────────────────────────────────────────────────────────

def test_uploads_are_archived_with_every_file(uploads):
    result = bk.backup_uploads()

    assert result["skipped"] is None
    assert result["file_count"] == 3, "not every uploaded file made it into the archive"
    assert os.path.isfile(result["path"])

    with tarfile.open(result["path"], "r:gz") as tar:
        names = sorted(m.name.replace("\\", "/") for m in tar.getmembers() if m.isfile())
    assert names == ["1/brief.pdf", "1/evidence.png", "2/contract.pdf"]


def test_archived_bytes_are_the_real_bytes(uploads, tmp_path):
    """An archive that restores different bytes is worse than no archive."""
    result = bk.backup_uploads()
    out = tmp_path / "extracted"
    with tarfile.open(result["path"], "r:gz") as tar:
        tar.extractall(out)                      # noqa: S202 - our own archive, in a tmp dir
    assert (out / "1" / "brief.pdf").read_bytes() == b"%PDF-1.4 tenant one brief"
    assert (out / "2" / "contract.pdf").read_bytes() == b"%PDF-1.4 tenant two contract"


def test_tenant_directory_structure_survives(uploads, tmp_path):
    """Files are namespaced by tenant on disk; a restore that flattens them mixes firms."""
    result = bk.backup_uploads()
    with tarfile.open(result["path"], "r:gz") as tar:
        names = [m.name.replace("\\", "/") for m in tar.getmembers() if m.isfile()]
    assert all("/" in n for n in names), f"tenant directories were flattened: {names}"


def test_absent_uploads_directory_is_a_no_op_not_a_failure(tmp_path, monkeypatch):
    """A fresh install has no files. Failing there teaches people to ignore failed backups."""
    from app.services import storage
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path / "does-not-exist")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))

    result = bk.backup_uploads()
    assert result["skipped"] == "no uploads directory"
    assert result["file_count"] == 0


def test_a_partial_archive_is_never_left_behind(uploads, monkeypatch):
    """A crash mid-archive must not leave a truncated file that looks complete."""
    real_open = tarfile.open

    def _explode(name, mode="r", *a, **kw):
        if "w" in mode:
            raise OSError("disk full, halfway through")
        return real_open(name, mode, *a, **kw)

    monkeypatch.setattr(bk.tarfile, "open", _explode)
    with pytest.raises(OSError):
        bk.backup_uploads()

    leftovers = list(uploads["backups"].glob("uploads-*"))
    assert not leftovers, f"a partial archive survived the failure: {leftovers}"


def test_retention_prunes_old_archives(uploads, monkeypatch):
    monkeypatch.setenv("BACKUP_KEEP", "2")
    for _ in range(4):
        bk.backup_uploads()
    kept = sorted(uploads["backups"].glob("uploads-*.tar.gz"))
    assert len(kept) == 2, f"retention kept {len(kept)} archives, expected 2"


def test_verify_uploads_backup_detects_a_corrupt_archive(uploads):
    good = bk.backup_uploads()["path"]
    assert bk.verify_uploads_backup(good)["ok"] is True

    with open(good, "r+b") as f:                 # truncate it mid-stream
        f.truncate(12)
    bad = bk.verify_uploads_backup(good)
    assert bad["ok"] is False, "a truncated archive was reported as valid"
    assert bad["error"]


# ── integration with run_backup, on BOTH engines ───────────────────────────────

def test_run_backup_archives_uploads(client, uploads):
    """The fix itself: run_backup covers the files, whichever database is configured.

    On PostgreSQL this used to do nothing at all. `aurora_managed` is still the correct status
    for the DATABASE half — RDS owns it — so the assertion here is about the uploads half
    appearing in the record either way.
    """
    from app.db.session import get_db
    from app.main import app
    from app.services.backup import run_backup

    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        run = run_backup(db, trigger="test")
    finally:
        db.close()
        gen.close()

    assert run.status in ("success", "aurora_managed"), run.detail
    assert "uploads:" in (run.detail or ""), (
        f"run_backup did not archive the uploaded files — detail was {run.detail!r}. "
        f"On PostgreSQL this is the whole gap: RDS covers the rows and nothing covered "
        f"the bytes")
    assert "3 file(s)" in run.detail
    assert run.size_bytes > 0

    archives = list(uploads["backups"].glob("uploads-*.tar.gz"))
    assert len(archives) == 1, f"expected one uploads archive, found {archives}"


# ── the boot gate ──────────────────────────────────────────────────────────────

def test_production_refuses_to_boot_without_declared_file_durability(monkeypatch):
    monkeypatch.delenv("UPLOADS_BACKUP_DIR", raising=False)
    monkeypatch.delenv("UPLOADS_DURABLE_STORAGE", raising=False)

    from app.security_gate import storage_problems
    problems = storage_problems()
    assert problems, "an undeclared file-durability configuration was accepted"
    assert "data/uploads" in problems[0]


@pytest.mark.parametrize("env,value", [
    ("UPLOADS_BACKUP_DIR", "/mnt/durable/backups"),
    ("UPLOADS_DURABLE_STORAGE", "1"),
])
def test_either_declaration_satisfies_the_gate(monkeypatch, env, value):
    monkeypatch.delenv("UPLOADS_BACKUP_DIR", raising=False)
    monkeypatch.delenv("UPLOADS_DURABLE_STORAGE", raising=False)
    monkeypatch.setenv(env, value)

    from app.security_gate import storage_problems
    assert storage_problems() == []


def test_setting_backup_dir_alone_does_not_satisfy_the_gate(monkeypatch):
    """BACKUP_DIR defaults to ./backups — the same disk as the uploads it would protect.

    A default is not a decision. The operator has to name a durable location, or state that
    the uploads directory is already on one.
    """
    monkeypatch.delenv("UPLOADS_BACKUP_DIR", raising=False)
    monkeypatch.delenv("UPLOADS_DURABLE_STORAGE", raising=False)
    monkeypatch.setenv("BACKUP_DIR", "/some/where")

    from app.security_gate import storage_problems
    assert storage_problems(), "BACKUP_DIR alone was accepted as a durability declaration"
