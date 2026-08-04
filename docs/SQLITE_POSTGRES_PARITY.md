# SQLite ↔ PostgreSQL Parity Audit

**Date:** 2026-08-04 · **Sprint:** S2 — PostgreSQL Production-Readiness
**Companion tests:** [`tests/test_postgres_parity.py`](../tests/test_postgres_parity.py),
[`tests/test_migration_on_populated_db.py`](../tests/test_migration_on_populated_db.py)

S2's acceptance criterion is that **no known SQLite/PostgreSQL behavioural discrepancy remains
unexplained**. This is the audit. Where a discrepancy exists it is stated, and — wherever it
can be — asserted in a test, because prose decays and assertions do not.

Juriscite develops and tests on SQLite and runs on PostgreSQL/Aurora. That split is the single
largest source of "worked in dev, broke in prod" risk in the project.

---

## 1. Discrepancies found

### 1.1 Foreign keys are not enforced on SQLite — **REAL, mitigated**

SQLite defaults to `PRAGMA foreign_keys=0` and nothing in `app/db/config.py` turns it on. A
referential-integrity violation is therefore **silently accepted in dev and rejected in
production**, and `ondelete="CASCADE"` is a **no-op on SQLite** while it fires on PostgreSQL.

The app already compensates where it matters most. `_erase_ai_and_activity`
(`app/routers/account.py`) deletes conversations and messages **explicitly** rather than
relying on the declared cascade, precisely so DPDP erasure behaves identically on both. That
was a real bug once: "we deleted your data" was false on one backend and true on the other.

* Pinned by `test_foreign_keys_are_enforced_on_postgres` (Postgres lane).
* Erasure completeness is enumerated schema-wide by `tests/test_erasure_completeness.py`.

> **Not "fixed" by turning the pragma on.** Enabling `foreign_keys=ON` for SQLite would make
> dev stricter and is tempting, but it would change the behaviour of ~780 existing tests at
> once, and the risk it addresses is already covered by explicit deletes plus the Postgres
> lane. Recorded as a deliberate decision, not an oversight.

### 1.2 A failed statement aborts the whole transaction on PostgreSQL — **REAL, no defect found**

On PostgreSQL any error inside a transaction aborts it: every subsequent statement fails with
`current transaction is aborted, commands ignored until end of transaction block` until a
rollback. SQLite has no such rule — the failed statement fails and the session carries on.

The dangerous shape is an endpoint that catches an `IntegrityError` (duplicate email, say),
returns 400, and then writes an audit row on the same session. That works in dev and fails in
production.

**No instance of this was found**, and the full 785-test suite passes on real PostgreSQL.
Pinned in both directions anyway:

* `test_a_failed_statement_does_not_poison_the_rest_of_the_transaction` asserts the abort
  semantics and that a rollback restores the connection (Postgres lane).
* `test_duplicate_registration_leaves_the_session_usable` drives the same situation through
  the real API and runs on **both** lanes.

### 1.3 Migrations behave differently against populated tables — **REAL, fixed, was a live deploy hazard**

`530d6dd3a280` added `tenant_id` as `NOT NULL`, no default, no backfill, to `cases` and
`clients`. Against an empty database that always succeeds. Against a database with rows it
fails with `column "tenant_id" contains null values` and leaves the deploy half-applied.

**CI could not catch this by construction** — both lanes start empty, so the lane would have
gone green on precisely the migration that breaks a populated Aurora.

Fixed by creating a default tenant and backfilling both tables before enforcing the
constraint, written as literal `op.execute()` SQL because `op.get_bind()` returns `None` in
Alembic's offline (`--sql`) mode.

`tests/test_migration_on_populated_db.py` now runs the real chain against a separately-created
database with rows already in it. **Verified to catch the bug**: with the backfill disabled the
test fails with `NOT NULL constraint failed: _alembic_tmp_cases.tenant_id` — the same failure
a deploy would have hit.

### 1.4 Enum types are not idempotent on PostgreSQL — **REAL, fixed**

Seven enum types were created by upgrades and dropped by no downgrade. `CREATE TYPE` is not
idempotent, so a rolled-back deploy could not be re-applied — the second upgrade failed with
`type already exists`. The affected downgrades now `DROP TYPE IF EXISTS`, guarded on the
postgresql dialect. SQLite has no native enum type, so none of this is visible there.

Covered by `test_rollback_then_reapply` and `test_downgrade_to_base_and_back`.

### 1.5 Locking and concurrency — **REAL, was breaking CI**

SQLite serialises writers with a single file lock, so lock-contention bugs are invisible.
PostgreSQL has real lock modes, and `TRUNCATE` needs `ACCESS EXCLUSIVE`.

This took the CI lane down for four runs: a background scheduler job abandoned by
`shutdown(wait=False)`, plus sixteen leaked sessions sitting `idle in transaction`, held locks
into the next test's fixture. Diagnosed and fixed in S1 — see
[`CI_RELEASE_EVIDENCE.md`](CI_RELEASE_EVIDENCE.md) §4.

Covered by `test_concurrent_inserts_do_not_deadlock` (Postgres lane).

---

## 2. Checked and found NOT to be a discrepancy

Recorded because "we looked and it was fine" is worth as much as a finding, and stops the
next person re-deriving it.

| Candidate | Finding |
|---|---|
| `LIKE` / `ILIKE` case-sensitivity | **No occurrences anywhere** in `app/` — the difference cannot arise. |
| JSON columns | Three (`billing.limits`, `user_activity.meta`, workbench). All use SQLAlchemy's generic `JSON` type with no dialect-specific operators (`->>`, `@>`, `.astext`, JSONB). Portable. |
| Raw SQL in app code | Four sites, all plain ANSI: `SELECT 1` health check, a `tenant_id` lookup, and two in the legacy `app/db/migrate_tenancy.py` helper. No dialect-specific syntax. |
| Result ordering without `ORDER BY` | 32 list queries in routers; 21 have `order_by`. All 11 without it were inspected individually: 9 are erasure/collection paths that iterate to delete, 1 builds a **set** for idempotency dedup (`ecourts.py`), and 1 is an inner sub-query whose outer query *does* order and limit (`workbench.py`). **No user-facing list depends on implicit order.** |
| Backups | `run_backup()` already dispatches on the driver and returns `status="aurora_managed"` on PostgreSQL; the tests assert per-backend behaviour. Not a divergence — but see the caveat below. |
| String concat / integer division | No `\|\|` concatenation or integer-division-dependent arithmetic in app code. |

---

## 3. Things that are *not* parity issues but are still open

* **The RDS-managed backup path has never been configured or restore-tested.** Parity is
  fine — the code correctly does nothing on PostgreSQL because RDS owns durability. Whether
  RDS *is* configured is a separate, open question (B3).
* **The local `./legal_server.db` is several migrations behind** and is missing the tenancy
  indexes entirely. Harmless — it is a gitignored dev artifact and no test uses it — but it
  is why the first draft of the index test reported four missing indexes that are in fact
  present in the models and in every migrated database. Run `alembic upgrade head` locally to
  resync it. **Never inspect `app.db.config.engine` from a SQLite test**; use the engine the
  `client` fixture is actually bound to.
* **Rate limiting is per-process.** Unrelated to the database, but the same class of
  "works on one box, breaks on many" risk. Do not scale horizontally until it is shared.

---

## 4. How this is kept true

| Guarantee | Mechanism |
|---|---|
| The full suite passes on real PostgreSQL | CI `test-postgres` job, **blocking**, `postgres:16` service container |
| Migrations apply to a populated database | `tests/test_migration_on_populated_db.py`, both lanes |
| Rollback and re-apply work | `test_rollback_then_reapply`, `test_downgrade_to_base_and_back` |
| Tenant isolation holds on PostgreSQL | `test_tenant_isolation_holds_on_the_configured_database`, both lanes |
| Tenant-scoped queries use an index | `test_every_tenant_scoped_hot_table_has_a_tenant_id_index` (both) plus `test_tenant_scoped_query_uses_the_index_at_scale` — see §5 for why the *shape* of that data matters more than its size |

**Reproducibility:** the PostgreSQL lane cannot be run on the current dev box (no Docker, no
local PostgreSQL). CI is the only place it executes; its JUnit XML artifact uploads with
`if: always()` so a failure is machine-readable. This is the one S2 acceptance criterion —
"PostgreSQL suite is reproducible locally/CI" — that is met **only** on the CI half.

**Evidence the PostgreSQL-only tests actually run.** A test that skips silently is
indistinguishable from one that passes, and this project has been bitten by exactly that
class of thing before. These are known to execute on the Postgres lane because they have been
seen to *fail* there — three of them in run #18 and one in run #20 — which a skipped test
cannot do. They pass on run #21 with the same `skipif` condition unchanged.

---

## 5. Two mistakes made writing this, kept because they generalise

**Inspecting the wrong database.** The index test first read `app.db.config.engine`. On the
Postgres lane that *is* the database under test; on SQLite it is the developer's real
`./legal_server.db`, which is several migrations behind. It confidently reported four missing
`tenant_id` indexes that are present in the models and in every migrated database. The rule
that came out of it: **never inspect `app.db.config.engine` from a test** — take the engine
the `client` fixture is bound to.

**Asserting something false about the planner.** The same test then seeded 5,000 rows split
*evenly* across two tenants and asserted an index scan. PostgreSQL returned

```
Seq Scan on clients  (cost=0.00..109.50 rows=2500)  Filter: (tenant_id = '1')
```

which is the **correct** plan — a query matching half a table is faster read sequentially.
Row count was never the variable; **selectivity** is. Rebuilt with the shape multi-tenancy
actually has: one target tenant with 25 clients beside a noise tenant with 5,000, `ANALYZE`d
so the planner works from statistics. At ~0.5% selectivity an index scan is unambiguously
right and a sequential scan is a real defect.

Both were caught by the Postgres lane rather than by review, which is the argument for having
the lane at all. Both were also *my* defects rather than the app's — worth stating, because a
red parity lane is not automatically evidence of a parity bug.
