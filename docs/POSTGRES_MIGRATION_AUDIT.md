# Postgres / Aurora migration audit — 2026-07-30

Static audit of all 16 Alembic migrations against the PostgreSQL dialect, plus the state of
the CI "Aurora rehearsal" lane. Performed without a Postgres server: the DDL was compiled
for the real dialect using Alembic **offline mode**
(`alembic upgrade head --sql` with a `postgresql+psycopg://` URL), which exercises the
dialect compiler without connecting to anything.

## Summary

| | |
|---|---|
| Migrations | 16, single head `e2b7c9d40a15`, no branching |
| Compile to Postgres DDL | ✅ all 16, 760 lines, exit 0 |
| Downgrade compiles | ✅ 322 lines, exit 0 |
| **Blocking deploy hazards** | **2 (below)** |
| CI lane status | **has never run** — no git remote |
| CI suite step | **non-blocking** (`continue-on-error: true`) |

The good news first, because it is real: `db/config.py` already branches correctly
(`check_same_thread` only for SQLite; `pool_pre_ping`, `pool_recycle` and a 5s
`connect_timeout` for Aurora), `migrations/env.py` honours `DATABASE_URL`, and every
`batch_alter_table` compiles to plain `ALTER TABLE` on Postgres without incident. `SERIAL`,
`TIMESTAMP WITHOUT TIME ZONE DEFAULT (CURRENT_TIMESTAMP)` and `CREATE TYPE … AS ENUM` all
render correctly.

---

## HAZARD 1 — the tenancy migration cannot be applied to a database that has data

`530d6dd3a280_sync_schema_to_models_catch_up.py` (lines 202, 206) adds a **NOT NULL column
with no default and no backfill** to two tables that already exist and, in production, hold
rows:

```sql
ALTER TABLE cases   ADD COLUMN tenant_id INTEGER NOT NULL;
ALTER TABLE clients ADD COLUMN tenant_id INTEGER NOT NULL;
```

On Postgres this fails outright: `column "tenant_id" of relation "cases" contains null
values`. The migration contains zero `execute`/`UPDATE` statements — there is no backfill.

**The CI lane cannot catch this, by construction.** CI starts from an empty
`postgres:16` container, every table has zero rows, and adding a NOT NULL column to an empty
table always succeeds. The lane will go green on precisely the migration that breaks a
populated Aurora.

A backfill *does* exist — `app/db/migrate_tenancy.py` creates a "Default Firm" tenant and
stamps existing rows — but it is **never called from anywhere** in the app, and it is
SQLite-only (`PRAGMA table_info(...)`). So the logic that would make this safe is both
orphaned and non-portable.

The other two NOT NULL adds are safe; they carry defaults
(`verification_status DEFAULT 'pending'`, `is_banned DEFAULT false`).

**Fix:** add the column nullable, backfill, then set NOT NULL — all inside the migration, in
portable SQLAlchemy Core rather than PRAGMA.

## HAZARD 2 — a rolled-back deploy cannot be re-applied

Seven enum types are created on the way up:

`casestatus`, `paymentmode`, `feetype`, `hearingstatus`, `hearingstage`, `hearingoutcome`,
`userrole`

The downgrade DDL contains **zero `DROP TYPE` statements**. Postgres enum types are
schema-level objects that outlive their tables, and `CREATE TYPE` is not idempotent.

So: `downgrade` succeeds, and the following `upgrade` fails with
`type "casestatus" already exists`. On Aurora a failed deploy that rolls back leaves the
database unable to move forward again without manual `DROP TYPE`. This is invisible on
SQLite, which has no enum types at all — the enum is just a `VARCHAR` check.

**Fix:** drop the types explicitly in the corresponding `downgrade()`.

---

## The lane itself

Two problems independent of any migration:

1. **It has never executed.** There is no git remote, so the workflow has never fired. "CI
   Postgres lane" is a file, not a result. Marking S0.4 complete records the intent, not the
   outcome.
2. **Its main step is disabled.** `continue-on-error: true` on the suite means a red
   Postgres run does not fail CI. Only `alembic upgrade head` is blocking — and per Hazard 1
   that step passes for the wrong reason.

## What is still unverified

This audit is static. It proves the migrations **compile** for Postgres; it cannot prove
they **run**, and it says nothing about the ~766 tests, which have only ever executed
against SQLite. Specifically untested:

* runtime query behaviour — though a grep found **no** `LIKE`/`ilike` usage in `app/` or
  `tests/`, so the classic SQLite-vs-Postgres case-sensitivity trap does not apply here
* transaction and isolation semantics under the scheduler's `UNIQUE(job_id, slot_key)` claim

Running the suite against a real Postgres remains the only way to close these. It needs
either a local Postgres/Docker (neither is installed on this machine) or the CI lane
actually running.

### Correction — backups are NOT a Postgres gap

An earlier version of this document stated that `app/services/backup.py` is SQLite-only and
"will not work on Aurora". **That is wrong**, and it was inferred from `import sqlite3` and
`PRAGMA integrity_check` at the top of the file without reading the dispatch twenty lines
below. `run_backup()` branches on the driver:

```python
elif driver == "postgresql":
    run.status = "aurora_managed"
    run.location = "Amazon RDS automated backups (PITR + daily snapshots)"
```

On Aurora, backups are deliberately delegated to RDS — point-in-time recovery plus daily
snapshots — and the app records that fact instead of attempting its own. The tests already
know this: `tests/test_backups.py` computes `IS_SQLITE` from the engine URL, skips the
file-retention tests on other backends, and asserts `status == "aurora_managed"` on
Postgres.

Which also means the suite is more Postgres-ready than this audit first assumed.
