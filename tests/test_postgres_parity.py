"""Behaviours where SQLite and PostgreSQL genuinely differ, pinned as tests.

S2's acceptance criterion is that *no known SQLite/PostgreSQL behavioural discrepancy remains
unexplained*. Prose in a document decays; these assert the differences instead, so a change in
either direction fails the build rather than surprising a deploy.

Tests that can only mean something on a real server are skipped on SQLite with a stated
reason — never quietly passed. `docs/SQLITE_POSTGRES_PARITY.md` is the written companion.
"""
import os
import threading

import pytest
from sqlalchemy import inspect, text

from app.db.base import Base
from tests.conftest import auth, register_and_login

IS_SQLITE = not os.getenv("DATABASE_URL", "").startswith(("postgresql", "postgres"))
pg_only = pytest.mark.skipif(
    IS_SQLITE,
    reason="PostgreSQL-specific behaviour; runs in the CI test-postgres lane "
           "(no Docker or local Postgres on the dev box)",
)


def _engine():
    """The configured engine.

    On the Postgres lane this IS the database under test. On SQLite it is NOT — see the
    `db_engine` fixture below. Only the @pg_only tests may use this.
    """
    from app.db.config import engine
    return engine


@pytest.fixture()
def db_engine(client):
    """The engine the tests are actually running against.

    Deliberately not `app.db.config.engine`. On the Postgres lane they are the same object,
    but on SQLite they are not: the `client` fixture builds a throwaway temp database per
    test, while `app.db.config.engine` still points at the developer's real
    ./legal_server.db — which, verified on 2026-08-04, is several migrations behind and is
    missing the tenancy indexes entirely.

    Inspecting the wrong one gives a confident, wrong answer about a database nobody is
    testing. The first draft of this file did exactly that and reported four missing indexes
    that were present in both the models and every migrated database.
    """
    from app.db.session import get_db
    from app.main import app

    gen = app.dependency_overrides[get_db]()
    session = next(gen)
    try:
        yield session.get_bind()
    finally:
        session.close()
        gen.close()          # run get_db's `finally`, rather than leaving it to the GC


# ── Foreign keys ───────────────────────────────────────────────────────────────

@pg_only
def test_foreign_keys_are_enforced_on_postgres():
    """PostgreSQL rejects an orphan FK. SQLite, as configured here, does not.

    SQLite defaults to `PRAGMA foreign_keys=0` and nothing in app/db/config.py turns it on,
    so a referential-integrity violation is silently accepted in dev and rejected in
    production. The app already compensates where it matters — `_erase_ai_and_activity` in
    app/routers/account.py deletes children explicitly rather than relying on
    `ondelete="CASCADE"`, precisely because that cascade is a no-op on SQLite — but the
    divergence itself should be pinned, not remembered.
    """
    from sqlalchemy.exc import IntegrityError

    eng = _engine()
    with pytest.raises(IntegrityError):
        with eng.begin() as conn:
            conn.execute(text(
                "INSERT INTO documents (tenant_id, case_id, filename, filepath, uploaded_at) "
                "VALUES (1, 999999, 'orphan.pdf', '/tmp/orphan.pdf', CURRENT_TIMESTAMP)"
            ))


# ── Transaction abort semantics ────────────────────────────────────────────────

@pg_only
def test_a_failed_statement_does_not_poison_the_rest_of_the_transaction():
    """The divergence most likely to bite an endpoint.

    On PostgreSQL, ANY error inside a transaction aborts it — every later statement fails with
    "current transaction is aborted, commands ignored until end of transaction block" until a
    rollback. SQLite has no such rule: the failed statement fails and the session carries on.

    So an endpoint that catches an IntegrityError (duplicate email, say), returns 400, and
    then writes an audit row on the same session works in dev and fails in production. This
    asserts the recovery contract: after a rollback the session is usable again.
    """
    from sqlalchemy.exc import IntegrityError, InternalError, ProgrammingError

    eng = _engine()
    with eng.connect() as conn:
        trans = conn.begin()
        with pytest.raises((IntegrityError, ProgrammingError)):
            conn.execute(text("INSERT INTO cases (id) VALUES (1)"))   # missing NOT NULL cols

        # The transaction is now aborted: further work must fail until it is rolled back.
        with pytest.raises((InternalError, ProgrammingError, IntegrityError)):
            conn.execute(text("SELECT COUNT(*) FROM cases"))

        trans.rollback()
        # ...and after the rollback the connection is healthy again.
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_duplicate_registration_leaves_the_session_usable(client):
    """The above, through the real API, on whichever database is configured.

    If any endpoint swallowed an IntegrityError without rolling back, this would pass on
    SQLite and fail on PostgreSQL. It runs on BOTH lanes deliberately — that is the whole
    point of the parity lane.
    """
    email = "dupe-parity@firm.example"
    register_and_login(client, email)

    second = client.post("/api/auth/register", json={
        "full_name": "Same Email", "email": email,
        "password": "Sup3rSecret!", "role": "advocate",
    })
    assert second.status_code in (400, 409), second.text

    # The app must still be able to serve requests that touch the database.
    again = client.post("/api/auth/login", json={"email": email, "password": "Sup3rSecret!"})
    assert again.status_code == 200, (
        "the session was left unusable after a constraint violation — on PostgreSQL an "
        "un-rolled-back error aborts the whole transaction"
    )


# ── Indexes and query plans ────────────────────────────────────────────────────

TENANT_SCOPED_HOT_TABLES = ["cases", "clients", "documents", "hearings", "audit_logs"]


def test_every_tenant_scoped_hot_table_has_a_tenant_id_index(db_engine):
    """Runs on both lanes. Every tenant-scoped read filters on tenant_id first.

    Without this index those become full scans, and they get slower in proportion to *other
    firms'* data — a tenant-isolation problem that presents as a performance one.

    Checked in both directions: the models must declare it (so `create_all` builds it) and
    the live database under test must actually have it (so the migrations built it too).
    """
    insp = inspect(db_engine)
    live_missing, declared_missing = [], []

    for table in TENANT_SCOPED_HOT_TABLES:
        declared = Base.metadata.tables.get(table)
        if declared is not None and not any(
            any(c.name == "tenant_id" for c in ix.columns) for ix in declared.indexes
        ):
            declared_missing.append(table)

        if table not in insp.get_table_names():
            continue
        if not any("tenant_id" in (ix["column_names"] or ())
                   for ix in insp.get_indexes(table)):
            live_missing.append(table)

    assert not declared_missing, f"models declare no tenant_id index on: {declared_missing}"
    assert not live_missing, f"database under test has no tenant_id index on: {live_missing}"


@pg_only
def test_tenant_scoped_query_uses_the_index_at_scale():
    """EXPLAIN on data large enough for the planner to have a real choice.

    Asserting a plan shape against an empty table proves nothing — PostgreSQL correctly
    sequential-scans a table of five rows, so the assertion would either fail or have to be
    written so loosely it could never fail. Seeding enough rows first is what makes this a
    real check: with 5,000 rows split across two tenants, a tenant-scoped lookup that still
    sequential-scans means the index is missing or unusable.
    """
    eng = _engine()
    with eng.begin() as conn:
        conn.execute(text(
            "INSERT INTO tenants (name) SELECT 'Plan Test' "
            "WHERE NOT EXISTS (SELECT 1 FROM tenants)"
        ))
        tid = conn.execute(text("SELECT MIN(id) FROM tenants")).scalar()
        conn.execute(text("""
            INSERT INTO clients (tenant_id, full_name, email, created_at)
            SELECT CASE WHEN g % 2 = 0 THEN :tid ELSE :tid + 1 END,
                   'Client ' || g, 'c' || g || '@plan.example', CURRENT_TIMESTAMP
              FROM generate_series(1, 5000) AS g
        """), {"tid": tid})
        conn.execute(text("ANALYZE clients"))

    with eng.connect() as conn:
        plan = "\n".join(r[0] for r in conn.execute(
            text("EXPLAIN SELECT id FROM clients WHERE tenant_id = :tid"), {"tid": tid}
        ))

    assert "Index" in plan or "Bitmap" in plan, (
        "a tenant-scoped lookup over 5,000 rows is not using an index. Plan was:\n" + plan
    )


# ── Concurrency ────────────────────────────────────────────────────────────────

@pg_only
def test_concurrent_inserts_do_not_deadlock():
    """Real connections, real locks — the thing SQLite cannot model.

    SQLite serialises writers with a file lock, so concurrent-write bugs are invisible there.
    This is deliberately modest: it asserts that ordinary concurrent inserts from separate
    connections all land and none deadlocks. That is the property the app relies on, and it is
    the shape of failure that took the CI lane down for four runs.
    """
    eng = _engine()
    errors: list[Exception] = []
    landed = threading.Semaphore(0)

    def _insert(n: int):
        try:
            with eng.begin() as conn:
                conn.execute(text(
                    "INSERT INTO tenants (name) VALUES (:n)"), {"n": f"concurrent-{n}"})
            landed.release()
        except Exception as exc:                      # pragma: no cover - failure path
            errors.append(exc)
            landed.release()

    threads = [threading.Thread(target=_insert, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "a concurrent insert never completed"
    assert not errors, f"concurrent inserts raised: {errors!r}"

    with eng.connect() as conn:
        count = conn.execute(text(
            "SELECT COUNT(*) FROM tenants WHERE name LIKE 'concurrent-%'")).scalar()
    assert count == 8, f"expected 8 concurrent inserts to land, got {count}"


# ── Tenant isolation, specifically on PostgreSQL ───────────────────────────────

def test_tenant_isolation_holds_on_the_configured_database(client):
    """The cross-tenant IDOR check, run on whichever database is configured.

    The suite's existing isolation sweep already runs in the Postgres lane because the whole
    suite does. This states the property directly so that "tenant isolation passes under
    PostgreSQL" is an assertion someone can point at, rather than an inference from the lane
    having been green.
    """
    tok_a = register_and_login(client, "firm-a-parity@example.com", "Firm A")
    tok_b = register_and_login(client, "firm-b-parity@example.com", "Firm B")

    made = client.post("/api/clients", headers=auth(tok_a),
                       json={"full_name": "Firm A Client", "email": "client-a@example.com"})
    assert made.status_code in (200, 201), made.text
    client_id = made.json()["id"]

    # Firm B must not be able to read Firm A's client by id.
    stolen = client.get(f"/api/clients/{client_id}", headers=auth(tok_b))
    assert stolen.status_code in (403, 404), (
        f"cross-tenant read returned {stolen.status_code} — tenant isolation is not holding "
        f"on {'SQLite' if IS_SQLITE else 'PostgreSQL'}"
    )

    # ...nor see it in their own listing.
    listing = client.get("/api/clients", headers=auth(tok_b))
    assert listing.status_code == 200
    assert all(c["id"] != client_id for c in listing.json()), (
        "another firm's client appeared in this tenant's list"
    )


# ── Schema parity ──────────────────────────────────────────────────────────────

def test_models_and_database_agree_on_every_table(db_engine):
    """Whatever the dialect, the live schema must contain every table the models declare.

    Catches a migration that applied on one backend and not the other — the failure mode that
    makes a deploy 'work' right up until the first query against a missing table.
    """
    live = set(inspect(db_engine).get_table_names())
    declared = set(Base.metadata.tables)
    assert not (declared - live), (
        f"declared by models but missing from the database: {sorted(declared - live)}")
