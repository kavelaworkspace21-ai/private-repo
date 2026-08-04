"""Application models must match what the migrations actually build (Phase 4, item 4).

Drift between `Base.metadata` and the migration chain is invisible in local development —
tests build their schema with `create_all` (from the models), while production builds it
with Alembic (from the migrations). When those disagree, the difference only appears in
production, as a missing column or a nullability violation on real data.

This builds a database the way PRODUCTION does — an empty DB run through every migration —
and compares it against the models. It is the check that would have caught the recorded
`misuse_reports.created_at` nullability drift.
"""
import os
import tempfile

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401 — registers every model on Base.metadata
from app.db.base import Base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Differences we have consciously accepted, with the reason. Anything NOT listed here
# fails the test — the point is that drift must be a decision, not a discovery.
ACCEPTED_DRIFT = {
    # ("kind", "table", "column")
    ("modify_nullable", "misuse_reports", "created_at"):
        "Known, tracked in docs/OWNER_QUEUE.md: model says NOT NULL, migration head says "
        "nullable. Tightening it needs a data check that no existing rows are null.",
}


@pytest.fixture(scope="module")
def migrated_engine():
    """An empty database taken through the full migration chain — the production path.

    NOTE: `cfg.set_main_option("sqlalchemy.url", ...)` is INERT here. migrations/env.py
    unconditionally overwrites it from the DATABASE_URL environment variable (defaulting
    to ./legal_server.db), so the env var is the only way to redirect a migration run.
    Setting the Config alone silently migrates the developer's own database instead.
    """
    from alembic import command

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite:///{path}"

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        cfg = Config(os.path.join(ROOT, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(ROOT, "migrations"))
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

    engine = create_engine(url)
    # Guard against the failure this fixture is prone to: if the migration ran somewhere
    # else, the comparison below would report every table as "missing" and look like
    # catastrophic drift rather than a broken fixture.
    assert inspect(engine).get_table_names(), (
        "the migration chain produced an empty database — it ran against the wrong URL")

    yield engine
    engine.dispose()
    try:
        os.remove(path)
    except OSError:
        pass


def _describe(diff) -> tuple:
    """Normalise an Alembic diff entry to (kind, table, column)."""
    if isinstance(diff, list):          # grouped column modifications
        diff = diff[0]
    kind = diff[0]
    if kind in ("add_table", "remove_table"):
        return (kind, diff[1].name, None)
    if kind in ("add_column", "remove_column"):
        return (kind, diff[2], diff[3].name)
    if kind.startswith("modify_"):
        return (kind, diff[2], diff[3])
    if kind in ("add_index", "remove_index", "add_constraint", "remove_constraint"):
        return (kind, getattr(diff[1], "table", None).name if getattr(diff[1], "table", None) else None,
                getattr(diff[1], "name", None))
    return (kind, None, None)


def test_models_match_the_migrated_schema(migrated_engine):
    with migrated_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diffs = compare_metadata(ctx, Base.metadata)

    unexpected = []
    for d in diffs:
        key = _describe(d)
        if key in ACCEPTED_DRIFT:
            continue
        # SQLite reflects some index/constraint detail imprecisely; those are noise here
        # and are covered on the real backend by the PostgreSQL lane.
        if key[0] in ("add_index", "remove_index", "add_constraint", "remove_constraint"):
            continue
        unexpected.append(key)

    assert not unexpected, (
        "models and migrations disagree — production builds its schema from migrations, "
        f"tests build it from models, so this only surfaces in production: {unexpected}")


def test_accepted_drift_is_still_real(migrated_engine):
    """If an accepted drift gets fixed, stop carrying the exemption.

    An allowlist that outlives its entries quietly stops protecting anything.
    """
    with migrated_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        present = {_describe(d) for d in compare_metadata(ctx, Base.metadata)}

    stale = [k for k in ACCEPTED_DRIFT if k not in present]
    assert not stale, (
        f"these drifts are recorded as accepted but no longer occur — remove them from "
        f"ACCEPTED_DRIFT: {stale}")


def test_tenant_scoped_tables_index_tenant_id(migrated_engine):
    """Every tenant-scoped table must index tenant_id.

    Each query filters on it. Unindexed it is a full scan per request — invisible on a
    local SQLite file with a handful of rows, and a production problem on Aurora.
    """
    insp = inspect(migrated_engine)
    missing = []
    for table in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns(table)}
        if "tenant_id" not in cols:
            continue
        indexed = {c for ix in insp.get_indexes(table) for c in ix["column_names"]}
        if "tenant_id" not in indexed:
            missing.append(table)

    assert not missing, f"tenant-scoped tables with no index on tenant_id: {missing}"
