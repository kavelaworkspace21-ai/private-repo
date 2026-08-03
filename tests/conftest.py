"""
Pytest fixtures: a FastAPI TestClient backed by a throwaway SQLite database,
so API/tenant tests never touch the real legal_server.db.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Tests must NEVER reach a real model provider: hard-set the keys empty BEFORE the app
# imports. (setdefault is not enough — PowerShell's `$env:X=""` DELETES the var, and the
# app's load_dotenv() would then fill AI_API_KEY from .env and CI would silently call NVIDIA.)
os.environ["AI_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
# Disable IP rate limiting during tests (all requests share one host → would false-trip).
os.environ["RATELIMIT_ENABLED"] = "0"
# Declare the test environment EXPLICITLY. app/security_gate.py refuses to boot with weak
# or absent signing secrets, and treats an unset ENVIRONMENT as production so that
# forgetting it fails closed. Tests legitimately run with throwaway secrets, so they must
# say so rather than have the gate relaxed on their behalf.
os.environ["ENVIRONMENT"] = "test"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import app.models  # noqa: F401  registers all models on Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture(scope="session")
def _pg_schema():
    """Build the Postgres schema ONCE for the whole session.

    It used to be built per test — `drop_all` + `create_all` + `drop_all` again, for every
    one of ~780 tests. On SQLite that is nearly free. On Postgres each one is catalog DDL
    against a real server: ~40 tables, their indexes and 7 enum types, three times over,
    per test.

    Measured, not guessed: the CI Postgres job was CANCELLED at 45 minutes, then again at
    90, having still not finished — while the identical suite takes ~8 minutes on SQLite.
    No timeout would ever have been enough, because the cost scales with the test count.
    The original comment called it "slower but this is a rehearsal, not the hot path",
    which was a fair guess that had never been measured, because the lane had never run.
    """
    from sqlalchemy import event, text

    from app.db.config import engine as configured_engine

    # FAIL FAST INSTEAD OF HANGING. drop_all, create_all and TRUNCATE all need an ACCESS
    # EXCLUSIVE lock. If any pooled connection is idle-in-transaction holding those tables,
    # Postgres waits FOREVER — there is no default lock timeout. SQLite has no such concept,
    # which is precisely why this is invisible locally.
    #
    # That is what the CI lane has been doing: runs #4, #5, #7 and #9 were cancelled at 45m,
    # 90m, 90m and 90m having emitted ~14 lines of pytest output. Near-silence under `-q` is
    # a block, not slowness. A 10s lock_timeout converts an unbounded hang into an
    # immediate, named error naming the statement that could not get its lock.
    @event.listens_for(configured_engine, "connect")
    def _set_timeouts(dbapi_conn, _rec):            # pragma: no cover - PG lane only
        with dbapi_conn.cursor() as cur:
            cur.execute("SET lock_timeout = '10s'")
            cur.execute("SET idle_in_transaction_session_timeout = '30s'")

    # Drop any pooled connection before schema DDL: a connection this pool is holding is
    # exactly the one that would block the lock we are about to take.
    configured_engine.dispose()

    Base.metadata.drop_all(configured_engine)     # clear anything a prior run left behind
    Base.metadata.create_all(configured_engine)
    try:
        yield configured_engine
    finally:
        configured_engine.dispose()
        Base.metadata.drop_all(configured_engine)


@pytest.fixture()
def client(request):
    # Postgres/Aurora parity lane (S0.4): when DATABASE_URL points at a non-SQLite backend
    # (the CI test-postgres job), run the very same tests against the REAL configured engine
    # instead of a throwaway SQLite file — that is what makes the lane an Aurora rehearsal
    # rather than SQLite-in-disguise. The SQLite branch below is UNCHANGED — the default
    # local and CI runs behave exactly as before.
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and not db_url.startswith("sqlite"):
        from sqlalchemy import text

        configured_engine = request.getfixturevalue("_pg_schema")

        # Per-test isolation by TRUNCATE rather than DDL. Emptying ~40 small tables is
        # milliseconds; dropping and recreating them is seconds. RESTART IDENTITY keeps the
        # behaviour tests were written against — a fresh schema restarts every sequence, so
        # the first user is still id 1. CASCADE handles the foreign-key ordering that
        # drop_all was doing implicitly.
        tables = ", ".join(f'"{t}"' for t in Base.metadata.tables)
        if tables:
            # Return every pooled connection first. A connection left idle-in-transaction by
            # the previous test holds row locks on these tables, and TRUNCATE needs ACCESS
            # EXCLUSIVE — without this it waits on the pool's own leftovers. The lock_timeout
            # set in _pg_schema turns any remaining contention into a fast, named error
            # rather than a silent 90-minute stall.
            configured_engine.dispose()
            with configured_engine.begin() as conn:
                conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=configured_engine)

        def _override_get_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                yield c
        finally:
            app.dependency_overrides.clear()
            # No drop_all here: the schema belongs to the session fixture, which tears it
            # down once at the end. Dropping it per test is what made this lane unable to
            # finish, and it would also destroy the schema the next test expects to find.
            # Isolation is the TRUNCATE at setup above.
        return

    # ── default: fresh SQLite temp DB per test (local + CI `test` job) ──
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()
    try:
        os.remove(path)
    except OSError:
        pass


def register_and_login(client, email: str, name: str = "Test Advocate") -> str:
    """Register an advocate (own tenant) and return a valid access token."""
    r = client.post("/api/auth/register", json={
        "full_name": name, "email": email, "password": "Sup3rSecret!",
        "role": "advocate",
    })
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": "Sup3rSecret!"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token
    return token


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
