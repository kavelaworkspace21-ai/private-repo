"""Backup restore-drill — prove a backup is actually restorable (not silently corrupt)."""
import os
import sqlite3

from app.services.backup import _sqlite_backup, verify_backup


def test_backup_then_restore_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    src = str(tmp_path / "src.db")
    c = sqlite3.connect(src)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    c.execute("CREATE TABLE tenants (id INTEGER PRIMARY KEY)")
    c.execute("INSERT INTO users (email) VALUES ('a@b.com')")
    c.commit()
    c.close()

    dst, size = _sqlite_backup(src)
    assert size > 0 and os.path.exists(dst)

    res = verify_backup(dst)
    assert res["ok"] and res["integrity"] == "ok" and res["has_core"]

    # The restored copy actually carries the data.
    cc = sqlite3.connect(dst)
    n = cc.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    cc.close()
    assert n == 1


def test_verify_backup_flags_missing_core(tmp_path):
    p = str(tmp_path / "empty.db")
    sqlite3.connect(p).close()        # valid SQLite, but no app tables
    res = verify_backup(p)
    assert res["integrity"] == "ok" and res["has_core"] is False and res["ok"] is False
