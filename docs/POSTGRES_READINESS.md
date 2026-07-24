# PostgreSQL / Aurora readiness

**Date:** 2026-07-24 · **Against:** vision-alignment Phase 4
**Status:** partially verifiable — **no PostgreSQL and no Docker on this machine**

Every test that has ever passed for Juriscite passed on **SQLite**. Production is **Aurora
PostgreSQL**. This document records what was verified locally, what was found, and what
genuinely cannot be closed without a server.

---

## What could NOT be done here (and why)

`docker`, `psql`, `pg_ctl` and `initdb` are all absent from this box. The `psycopg` 3.3.4
driver is installed, but a driver is not a server. So Phase 4 items 1–3 — run the
migrations against real PostgreSQL, run the suite against it, and make the CI lane
blocking after its first clean run — **cannot be certified here**. They are not claimed.

The CI lane (`.github/workflows/ci.yml`, job `test-postgres`) already exists and runs
against a real `postgres:16`. Its `alembic upgrade head` step is **blocking**; the suite
step is still `continue-on-error: true`. It should be flipped to blocking after its first
clean run — deliberately not flipped blind from here, since a red pipeline that nobody
trusts is worse than an honest advisory one.

---

## What WAS verified locally

### 1. The codebase is portable at the SQL level — audited, not assumed

| Divergence hunted | Result |
|---|---|
| `LIKE` (case-**insensitive** on SQLite, case-**sensitive** on PostgreSQL) | **No SQL `LIKE`/`ILIKE` anywhere.** Text search runs through ChromaDB, not SQL — the classic silent-behaviour-change does not apply |
| SQLite-only SQL functions (`strftime`, `julianday`, `group_concat`) | **None in SQL.** Every `strftime` hit is Python `datetime.strftime` |
| `PRAGMA` / `sqlite_master` | Only in `app/services/backup.py`, which is explicitly the SQLite backup path (PostgreSQL delegates to RDS-managed snapshots) — by design |
| SQLite dialect imports | None |
| SQL functions in use | `func.now()` (×42) and `func.count()` — both portable |

### 2. Models match what the migrations actually build

`tests/test_schema_consistency.py` builds a database **the way production does** — an empty
DB through every migration — and compares it against `Base.metadata`. This matters because
tests build their schema with `create_all` (from models) while production uses Alembic
(from migrations); when those disagree, it only shows up in production.

Result: **models and migrations agree**, apart from one consciously accepted drift
(`misuse_reports.created_at` nullability, tracked in `OWNER_QUEUE.md`). A second test
asserts each accepted drift *still occurs*, so the allowlist cannot quietly outlive its
entries — and it doubles as proof the comparison isn't returning nothing.

### 3. Every tenant-scoped table indexes `tenant_id`

Checked against the migrated schema. Each request filters on `tenant_id`; unindexed it is a
full scan per request — invisible on a local SQLite file with a handful of rows, and a real
problem on Aurora under load.

---

## Open risk that needs a real server to settle

**`server_default=func.now()` into naive `DateTime` columns.** Every timestamp column in
this schema is naive (`app/util/time.py::utcnow()` deliberately writes naive UTC, because
the columns are naive). On SQLite, `CURRENT_TIMESTAMP` is UTC, so app-written and
DB-defaulted values agree. On PostgreSQL, `now()` returns `timestamptz`, and storing it
into `TIMESTAMP WITHOUT TIME ZONE` converts using the **server's** TimeZone setting. If the
Aurora instance is not on UTC, DB-defaulted timestamps would be local time while
app-written ones stay UTC — **two timezones mixed in one column**, with no error.

It would corrupt ordering, limitation-period arithmetic and audit chronology quietly, which
for this product is serious. It cannot be reproduced without a PostgreSQL server.

**Required before Aurora carries data:**
1. Set the cluster parameter group `timezone = UTC` (this alone makes the two agree), and
2. Verify after deployment that a DB-defaulted `created_at` and an app-written `utcnow()`
   written in the same second are within one second of each other.

---

## Checklist to close Phase 4 (needs owner infrastructure)

- [ ] Run all migrations from an empty PostgreSQL database
- [ ] Run all migrations from the last supported production schema
- [ ] Run the full suite on PostgreSQL — tenancy, transactions, date/time, pagination, JSON, scheduler claims, audit, consent, data rights, billing, deletes
- [ ] Confirm `timezone = UTC` on the cluster and verify the timestamp check above
- [ ] Flip the CI PostgreSQL suite to blocking after its first clean run
- [ ] Verify required indexes on the real backend under representative volume
- [ ] Restore an encrypted production-like backup into a clean environment and verify tenants, audit, documents, draft versions, jobs, consents, data-rights state
- [ ] Rehearse application, migration and corpus/index rollback

---

*Local verification only. Nothing here certifies PostgreSQL compatibility — it narrows what
remains to be proven on a real cluster.*
