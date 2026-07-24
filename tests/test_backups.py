"""
Phase B — automated database backups (CLAUDE.md §6 step 9 + §5 BackupRun).
A firm admin can trigger a backup → a real, non-empty SQLite copy + an auditable BackupRun.
Rolling retention prunes old files. Non-admins and unauthenticated callers are refused.
"""
import os
import glob

import pytest

from tests.conftest import register_and_login, auth

# Which backend is the app actually using? The SQLite online-backup path produces a real
# local file; on Postgres the endpoint delegates to RDS-managed backups (status
# "aurora_managed", no local file). Tests below branch/skip accordingly so they are green on
# BOTH the SQLite `test` lane and the Postgres `test-postgres` lane (S0.4).
from app.db.config import engine as _app_engine
IS_SQLITE = _app_engine.url.get_backend_name() == "sqlite"


def _admin(client, email):
    client.post("/api/auth/register", json={
        "full_name": "Firm Admin", "email": email, "password": "Sup3rSecret!", "role": "firm_admin"})
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


def test_admin_backup_creates_real_file(client, tmp_path):
    os.environ["BACKUP_DIR"] = str(tmp_path)
    try:
        admin = _admin(client, "badmin1@firm.com")
        r = client.post("/api/admin/backup", headers=auth(admin))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["trigger"] == "manual"
        if IS_SQLITE:
            assert body["engine"] == "sqlite"
            assert body["status"] == "success"
            assert body["size_bytes"] > 0
            assert os.path.exists(body["location"])
        else:
            # Postgres/Aurora: backups are RDS-managed, not a local file.
            assert body["engine"] == "postgresql"
            assert body["status"] == "aurora_managed"
    finally:
        os.environ.pop("BACKUP_DIR", None)


def test_backup_is_listed(client, tmp_path):
    os.environ["BACKUP_DIR"] = str(tmp_path)
    try:
        admin = _admin(client, "badmin2@firm.com")
        client.post("/api/admin/backup", headers=auth(admin))
        rows = client.get("/api/admin/backups", headers=auth(admin)).json()
        expected = "success" if IS_SQLITE else "aurora_managed"
        assert len(rows) >= 1 and rows[0]["status"] == expected
    finally:
        os.environ.pop("BACKUP_DIR", None)


@pytest.mark.skipif(not IS_SQLITE, reason="file-based retention is a SQLite-backup concept; "
                                          "Postgres backups are RDS-managed (no local files)")
def test_backup_retention_keeps_limit(client, tmp_path):
    os.environ["BACKUP_DIR"] = str(tmp_path)
    os.environ["BACKUP_KEEP"] = "2"
    try:
        admin = _admin(client, "badmin3@firm.com")
        for _ in range(4):
            assert client.post("/api/admin/backup", headers=auth(admin)).status_code == 200
        files = glob.glob(os.path.join(str(tmp_path), "legalserver-*.db"))
        assert len(files) == 2          # rolling retention pruned the 2 oldest
    finally:
        os.environ.pop("BACKUP_DIR", None)
        os.environ.pop("BACKUP_KEEP", None)


def test_backup_requires_admin(client):
    adv = register_and_login(client, "bnonadmin@firm.com")   # advocate, not firm_admin
    assert client.post("/api/admin/backup", headers=auth(adv)).status_code == 403
    assert client.get("/api/admin/backups", headers=auth(adv)).status_code == 403


def test_backup_requires_auth(client):
    assert client.post("/api/admin/backup").status_code in (401, 403)
    assert client.get("/api/admin/backups").status_code in (401, 403)
