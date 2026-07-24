"""
One-shot, idempotent tenancy migration for the SQLite dev DB.

Creates the tenants + audit_logs tables, adds tenant_id columns to users/clients/cases,
and backfills any existing rows into a single default tenant so nothing is orphaned.

Run:  python -m app.db.migrate_tenancy
"""
from sqlalchemy import text
from app.db.config import engine
from app.db.base import Base
import app.models  # noqa: F401  (registers all models on Base.metadata)


def _columns(conn, table) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def _add_column_if_missing(conn, table, column, ddl):
    if column not in _columns(conn, table):
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
        print(f"  + {table}.{column}")
    else:
        print(f"  = {table}.{column} (exists)")


def run():
    # 1) Create any missing tables (tenants, audit_logs) without touching existing ones
    Base.metadata.create_all(engine)

    # Child tables get tenant_id too (full §5 compliance); backfilled from parent case.
    CHILD_TABLES = (
        "hearings", "documents", "fees_collected", "fees_due",
        "diary_entries", "diary_tasks", "filing_deadlines", "opposing_counsel",
    )

    with engine.begin() as conn:
        # 2) Add tenant_id columns
        for table in ("users", "clients", "cases", *CHILD_TABLES):
            _add_column_if_missing(conn, table, "tenant_id", "tenant_id INTEGER")

        # 3) Ensure a default tenant exists for backfill
        existing = conn.execute(text("SELECT id FROM tenants ORDER BY id LIMIT 1")).fetchone()
        if existing:
            default_tid = existing[0]
        else:
            conn.execute(text("INSERT INTO tenants (name) VALUES ('Default Firm')"))
            default_tid = conn.execute(text("SELECT id FROM tenants ORDER BY id LIMIT 1")).fetchone()[0]
            print(f"  created default tenant id={default_tid}")

        # 4) Backfill NULL tenant_ids
        for table in ("users", "clients", "cases"):
            conn.execute(text(
                f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"
            ), {"tid": default_tid})

        # 5) Child rows inherit tenant from their parent case (authoritative source)
        for table in CHILD_TABLES:
            conn.execute(text(
                f"UPDATE {table} SET tenant_id = "
                f"(SELECT c.tenant_id FROM cases c WHERE c.id = {table}.case_id) "
                f"WHERE tenant_id IS NULL"
            ))
        print(f"  backfilled existing rows (parents to tenant {default_tid}, children from case)")

    print("Tenancy migration complete.")


if __name__ == "__main__":
    run()
