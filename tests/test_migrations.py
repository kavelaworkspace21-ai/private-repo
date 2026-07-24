"""
Guard against Alembic drift (CLAUDE.md §5: "Use Alembic migrations for all schema changes").
A fresh `alembic upgrade head` must produce EXACTLY the table set the ORM models define — so the
migration chain can never again silently fall behind the models (which is what happened pre-2026-06-22).
"""
import os
import tempfile


def test_single_alembic_head():
    """Exactly one migration head — guards against a branched/forked migration chain."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert len(heads) == 1, f"expected a single Alembic head, found: {heads}"


def test_alembic_head_matches_models():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    try:
        from alembic.config import Config
        from alembic import command
        command.upgrade(Config("alembic.ini"), "head")

        from sqlalchemy import create_engine, inspect
        import app.models  # noqa: F401 — registers all models on Base.metadata
        from app.db.base import Base

        engine = create_engine(os.environ["DATABASE_URL"])
        got = set(inspect(engine).get_table_names()) - {"alembic_version"}
        want = set(Base.metadata.tables)
        engine.dispose()
        assert got == want, f"Alembic head drifted from models: missing={want - got} extra={got - want}"
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        try:
            os.remove(path)
        except OSError:
            pass
