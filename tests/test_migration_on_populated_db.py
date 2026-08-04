"""Migrations must survive a database that already has data.

**CI cannot catch this by construction.** Both CI lanes start from an empty database, and on
an empty table `ADD COLUMN tenant_id INTEGER NOT NULL` always succeeds — there are no rows to
violate the constraint. So the lane would go green on precisely the migration that breaks a
populated Aurora. The only database that matters for this question is one with rows in it.

That is not hypothetical. `530d6dd3a280` added `tenant_id` as NOT NULL with no default and no
backfill, to `cases` and `clients`. Against the empty CI database: fine. Against the owner's
actual data: `column "tenant_id" contains null values`, migration aborts, deploy is stuck
half-applied. The fix — create a default tenant, then backfill both tables before enforcing
the constraint — is written in pure `op.execute()` SQL rather than through `op.get_bind()`,
because in Alembic's offline mode (`upgrade head --sql`) `get_bind()` returns None.

These tests run the real migration chain against a real, separately-created database, so they
exercise the same code path a deploy does. They run on **both** lanes: SQLite proves the chain
is coherent, PostgreSQL proves the DDL and the enum handling are.

Covers S2: "exercise migrations against representative populated data", "test rollback/
re-apply behaviour", "test enum creation/idempotency behaviour".
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parent.parent

# The last revision BEFORE tenancy landed. Data inserted here is data that predates
# tenant_id, which is exactly the shape of the owner's real database.
PRE_TENANCY_REV = "49bedae4c1dc"


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    """Run alembic against `url` in a subprocess.

    A subprocess, not the in-process API, on purpose: migrations/env.py resolves the URL from
    the DATABASE_URL environment variable at import time, and alembic caches module-level
    state. Driving it out-of-process is how a deploy actually invokes it, so it is also the
    honest thing to test.
    """
    env = dict(os.environ, DATABASE_URL=url)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )


def _assert_ok(result: subprocess.CompletedProcess, what: str) -> None:
    assert result.returncode == 0, (
        f"{what} failed (exit {result.returncode}).\n"
        f"--- stdout ---\n{result.stdout[-3000:]}\n--- stderr ---\n{result.stderr[-3000:]}"
    )


@pytest.fixture()
def isolated_db_url(tmp_path):
    """A database of this test's own, never the one the suite is using.

    These tests move the schema backwards and forwards through the revision chain. Doing that
    to the shared test database would destroy the schema every other test depends on.
    """
    configured = os.getenv("DATABASE_URL", "")

    if not configured or configured.startswith("sqlite"):
        yield f"sqlite:///{(tmp_path / 'migration_target.db').as_posix()}"
        return

    # PostgreSQL: create a genuinely separate database on the same server.
    url = make_url(configured)
    name = f"migration_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        yield str(url.set(database=name))
    finally:
        with admin.connect() as conn:
            # Terminate stragglers first — DROP DATABASE fails while anything is connected.
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"
            ), {"n": name})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _seed_pre_tenancy_rows(url: str) -> None:
    """Insert representative rows in the shape they had before tenant_id existed."""
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO clients (id, full_name, email, created_at) "
                "VALUES (1, 'Existing Client', 'existing@firm.example', CURRENT_TIMESTAMP)"
            ))
            conn.execute(text(
                "INSERT INTO cases (id, title, status, client_id, created_at, updated_at) "
                "VALUES (1, 'Pre-existing Matter', 'open', 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
    finally:
        engine.dispose()


def test_full_chain_applies_to_a_populated_database(isolated_db_url):
    """The headline case: upgrade a database that already has rows, and keep the rows."""
    _assert_ok(_alembic(isolated_db_url, "upgrade", PRE_TENANCY_REV),
               f"upgrade to {PRE_TENANCY_REV}")
    _seed_pre_tenancy_rows(isolated_db_url)

    _assert_ok(_alembic(isolated_db_url, "upgrade", "head"),
               "upgrade head over populated tables")

    engine = create_engine(isolated_db_url)
    try:
        with engine.connect() as conn:
            # The pre-existing rows are still there. A migration that "succeeds" by dropping
            # and recreating the table would pass a NOT NULL check and lose the firm's data.
            assert conn.execute(text("SELECT COUNT(*) FROM cases")).scalar() == 1
            assert conn.execute(text("SELECT COUNT(*) FROM clients")).scalar() == 1
            assert conn.execute(
                text("SELECT title FROM cases WHERE id = 1")).scalar() == "Pre-existing Matter"

            # ...and they were backfilled, not left null.
            for table in ("cases", "clients"):
                nulls = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")).scalar()
                assert nulls == 0, f"{table} has rows with a NULL tenant_id after migrating"

            # The backfilled tenant_id points at a tenant that exists.
            orphans = conn.execute(text(
                "SELECT COUNT(*) FROM cases c "
                "WHERE NOT EXISTS (SELECT 1 FROM tenants t WHERE t.id = c.tenant_id)"
            )).scalar()
            assert orphans == 0, "cases.tenant_id references a tenant row that does not exist"
    finally:
        engine.dispose()


def test_tenant_id_is_actually_enforced_after_migrating(isolated_db_url):
    """Backfilling must not have been achieved by quietly leaving the column nullable."""
    _assert_ok(_alembic(isolated_db_url, "upgrade", "head"), "upgrade head")

    engine = create_engine(isolated_db_url)
    try:
        cols = {c["name"]: c for c in inspect(engine).get_columns("cases")}
        assert "tenant_id" in cols, "cases.tenant_id is missing after upgrade head"
        assert cols["tenant_id"]["nullable"] is False, (
            "cases.tenant_id is nullable — the constraint the migration exists to add was not "
            "applied, so tenant isolation is not enforced at the database level"
        )
    finally:
        engine.dispose()


def test_rollback_then_reapply(isolated_db_url):
    """A rolled-back deploy must be re-appliable.

    This is the enum-idempotency case. Seven PostgreSQL enum types were created by upgrades
    and dropped by none, and `CREATE TYPE` is not idempotent — so re-running an upgrade after
    a downgrade failed with "type already exists". The affected downgrades now
    `DROP TYPE IF EXISTS`, guarded on the postgresql dialect.

    On SQLite this still proves the chain's downgrade path is coherent end to end.
    """
    _assert_ok(_alembic(isolated_db_url, "upgrade", "head"), "first upgrade head")
    _assert_ok(_alembic(isolated_db_url, "downgrade", PRE_TENANCY_REV),
               f"downgrade to {PRE_TENANCY_REV}")
    _assert_ok(_alembic(isolated_db_url, "upgrade", "head"),
               "re-apply upgrade head after a rollback")

    engine = create_engine(isolated_db_url)
    try:
        assert "cases" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_downgrade_to_base_and_back(isolated_db_url):
    """The whole chain, both directions. Catches a downgrade that silently does nothing."""
    _assert_ok(_alembic(isolated_db_url, "upgrade", "head"), "upgrade head")
    _assert_ok(_alembic(isolated_db_url, "downgrade", "base"), "downgrade base")

    engine = create_engine(isolated_db_url)
    try:
        remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
        assert not remaining, (
            f"downgrade to base left tables behind: {sorted(remaining)}. A downgrade that does "
            f"not undo its upgrade turns a rollback into a half-migrated database."
        )
    finally:
        engine.dispose()

    _assert_ok(_alembic(isolated_db_url, "upgrade", "head"), "upgrade head again from base")
