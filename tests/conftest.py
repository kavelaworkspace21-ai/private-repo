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

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import app.models  # noqa: F401  registers all models on Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client():
    # Postgres/Aurora parity lane (S0.4): when DATABASE_URL points at a non-SQLite backend
    # (the CI test-postgres job), run the very same tests against the REAL configured engine
    # instead of a throwaway SQLite file — that is what makes the lane an Aurora rehearsal
    # rather than SQLite-in-disguise. Per-test isolation is a clean drop_all/create_all on the
    # shared DB (the PG lane runs serially, so this is safe; it is slower but this is a
    # rehearsal, not the hot path). The SQLite branch below is UNCHANGED — the default local
    # and CI runs behave exactly as before.
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and not db_url.startswith("sqlite"):
        from app.db.config import engine as configured_engine

        Base.metadata.drop_all(configured_engine)     # clear anything a prior test left behind
        Base.metadata.create_all(configured_engine)
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
            Base.metadata.drop_all(configured_engine)
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
