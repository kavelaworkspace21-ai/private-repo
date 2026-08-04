# Aurora Deployment Runbook

**Sprint:** S3 — Aurora Deployment Rehearsal · **Written:** 2026-08-04 · **Status:** UNREHEARSED

> **Read this first.** No part of this has been executed against a real Aurora cluster,
> because none exists and agent AWS access is revoked. Every *command* here was verified
> against the code that implements it — the gates, endpoints, flags and thresholds are real
> and were read out of the source, not assumed — but the **procedure as a whole is untested**.
> The first run of it *is* the rehearsal. Expect to correct this document during that run;
> that is what it is for.
>
> What has been proven, in CI, against a real `postgres:16`:
> the full 795-test suite passes; `alembic upgrade head` applies from empty; the chain applies
> to a database **that already has rows**; rollback-then-reapply works. See
> [`CI_RELEASE_EVIDENCE.md`](CI_RELEASE_EVIDENCE.md) and
> [`SQLITE_POSTGRES_PARITY.md`](SQLITE_POSTGRES_PARITY.md).

---

## 0. Division of labour

| Owner does (AWS) | Agent has prepared |
|---|---|
| Provision Aurora PostgreSQL | This runbook |
| Networking, security groups, secrets | `scripts/smoke_test.py` |
| Run the migration commands below | The pre/post checklists |
| Run the smoke test, record timings | Rollback + recovery procedures |

Agent AWS access is revoked. Everything in the left column is yours.

---

## 1. Pre-deploy checklist

Every line is a gate. A gate you skip is a gate you do not have.

### 1.1 The build is the audited release

```bash
python -m app.ops.release preflight
```

Exit 0 means safe to deploy; exit 1 prints the blocking problems and **must stop the deploy**.
It fails closed on all of: app version drift, corpus fingerprint drift, vector-index count
mismatch, migration-head drift, a dirty working tree, a commit that is not the pinned release
commit, missing `JWT_SECRET` / `FIELD_ENCRYPTION_KEY`, and free disk below 500 MB.

It has caught real drift twice. Do not pass `--allow-dirty` or `--no-require-secrets` for a
production deploy — both exist for local checks only.

### 1.2 CI is green on the exact commit being deployed

Not "green on main" — green on **this commit**. All three jobs: `test`, `test-postgres`,
`audit`.

### 1.3 Environment variables

The app **refuses to boot** in production without these. `ENVIRONMENT` unset is treated as
production, so forgetting it fails closed rather than open.

| Variable | Requirement | Enforced by |
|---|---|---|
| `ENVIRONMENT` | `production` | `app/security_gate.py` |
| `DATABASE_URL` | `postgresql+psycopg://USER:PASS@host:5432/db?sslmode=require` | `database_problems()` |
| `JWT_SECRET` | ≥ 32 chars, not `change-me-in-production` | `secret_problems()` |
| `FIELD_ENCRYPTION_KEY` | a Fernet key | `secret_problems()` |
| `BILLING_MODE` | stays `test` until G6/G7 | `assert_billing_mode_allowed` |
| `KANOON_ENABLED` | `false` | governance |

> **`sslmode` is not optional and not a style preference.** libpq defaults to
> `sslmode=prefer`, which **silently falls back to an unencrypted connection** if the server
> does not offer TLS — client matter data would cross the network in the clear with no error
> and no log line. The boot gate rejects a `DATABASE_URL` with no `sslmode`, and rejects
> `disable` and `allow` explicitly. Use `require`, or `verify-full` with a CA bundle.

Generate secrets (never commit them, never paste them into a transcript):

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 1.4 Take a backup you have restored before

If the database has any data, snapshot it **and confirm the snapshot exists** before
migrating. See §6 — on PostgreSQL the app performs no backup of its own.

### 1.5 Know the rollback target

Record the current migration revision before touching anything:

```bash
alembic current
```

Write it down. §5 needs it, and after a failed migration is the worst time to go looking.

---

## 2. Migration procedure

### 2.1 Compile the DDL and read it, before running it

```bash
alembic upgrade head --sql > /tmp/aurora-upgrade.sql
```

Offline mode: emits the SQL without touching a server. Read it. This is the last point at
which a destructive statement is cheap to notice.

> In offline mode `op.get_bind()` returns `None`. Data migrations must therefore use
> `op.execute("...")` with literal SQL. The tenancy backfill in `530d6dd3a280` is written that
> way for exactly this reason — if a future migration breaks this command, that is why.

### 2.2 Apply

```bash
alembic upgrade head
```

### 2.3 Verify the head landed

```bash
alembic current
```

Must equal `migration_head` in `RELEASE.json` (`e2b7c9d40a15` as of this writing). Preflight
checks this too, and will refuse the deploy if it drifts.

### 2.4 If the database already had data

This is the case CI **cannot** test by construction — both lanes start empty, and on an empty
table `ADD COLUMN tenant_id NOT NULL` always succeeds. Against rows it fails with
`column "tenant_id" contains null values`, and leaves the deploy half-applied.

`tests/test_migration_on_populated_db.py` covers it: it runs the real chain against a
separately-created database that already has rows, and it is **verified to catch the bug** —
with the backfill disabled it fails exactly as a real deploy would. After migrating a
populated database, confirm by hand anyway:

```sql
SELECT COUNT(*) FROM cases   WHERE tenant_id IS NULL;   -- must be 0
SELECT COUNT(*) FROM clients WHERE tenant_id IS NULL;   -- must be 0
SELECT COUNT(*) FROM cases c
 WHERE NOT EXISTS (SELECT 1 FROM tenants t WHERE t.id = c.tenant_id);  -- must be 0
```

---

## 3. Application startup verification

Start the app, then — in order — confirm:

1. **It booted at all.** The boot gates raise `RuntimeError` rather than logging, so a
   misconfigured deploy *fails to start*. A process that is running has already passed
   `assert_secrets_sane()`, `assert_prohibited_disabled()` and `assert_soul_intact()`.
2. **Liveness**, which includes the database:

   ```bash
   curl -fsS https://YOUR_HOST/healthz
   ```

   `{"status":"ok","soul":"intact","db":"ok"}`. It runs `SELECT 1` through the app's own
   session, so a 200 proves the `DATABASE_URL` resolves, authenticates over TLS, and serves —
   from inside the deployed process, which is the only place that counts. Returns **503** if
   the soul is broken or the database is down, so a load balancer pulls the instance.
3. **Readiness:**

   ```bash
   curl -fsS https://YOUR_HOST/readyz
   ```

   `status: ready`, and `vector_index.chunks` equal to `vector_index.expected`.

> **Probe timeouts — this will bite you.** The **first** `/readyz` on a freshly-booted process
> opens the Chroma persistent store and loads the ONNX embedding model. Measured on the dev
> box: **3.95 s cold against 0.03 s warm**, and observed once to exceed **15 s** under
> concurrent load. A readiness probe with a 5 s timeout and 3 retries will kill instances that
> were about to become healthy, in a loop, and it will look like a crash. Allow a generous
> `initialDelaySeconds` and a `timeoutSeconds` well above 15. `/healthz` is cheap and is the
> right liveness probe; `/readyz` is the right *readiness* probe but is not cheap on the first
> call.
>
> `/readyz` never triggers a reseed and never probes the model — it only reports. A cold
> instance is slow once, not repeatedly.

---

## 4. Post-deploy verification

```bash
python scripts/smoke_test.py https://YOUR_HOST --admin-token "$ADMIN_TOKEN"
```

Exit 0 = every required check passed · 1 = a required check failed · 2 = usage error.

It checks liveness, database reachability from inside the app, soul integrity, readiness, the
vector-index count against the pinned one, release identity against `RELEASE.json`, that
authentication is enforced on protected routes, and that `/docs` is not public.

It **creates no data** — no test user, no matter — so it is safe against production. Without
`--admin-token` the release-identity check is **SKIPPED and reported as skipped**, never
silently passed; an unverifiable identity is not a verified one.

> **The token must belong to a user whose role is `firm_admin`.** `/api/admin/status` is
> guarded by `require_firm_admin = require_role(UserRole.firm_admin)`; an `advocate` token
> gets **403**, which the smoke test reports as a failure rather than a skip. Obtain one by
> logging in as the firm-admin account and taking `access_token` from the response.

Verified end to end on 2026-08-04 against a live local instance before being committed —
every branch, not just the happy path: exit 0 with all 14 checks passing (including release
identity with a real `firm_admin` token), exit 1 with five failures against a dead endpoint,
exit 1 on a rejected token, exit 2 refusing plaintext HTTP to a non-localhost host.

**Also confirm, once:**

* A real login works end to end (use an account you already control, not a new one).
* The vector-index count in `/readyz` matches `RELEASE.json` — a *built but wrong-sized* index
  still answers `/readyz` 200, because readiness only requires `chunks > 0`. Retrieval would
  then draw on a different corpus than the audited one. The smoke test asserts the equality
  that `/readyz` alone does not.

---

## 5. Rollback procedure

**Decide first: is this a rollback or a fix-forward?** A schema change that has already
accepted writes cannot be cleanly reversed — downgrading drops the columns those writes went
into. If real data has landed on the new schema, restore from backup (§6) rather than
downgrade.

### 5.1 Application only (schema unchanged)

Redeploy the previous image/commit. Nothing else to do.

### 5.2 Schema rollback

```bash
alembic downgrade <the revision recorded in §1.5>
```

Then redeploy the matching application version. **The app and the schema must move together** —
a new app against an old schema fails on the first query to a missing column.

### 5.3 Re-applying after a rollback

Verified to work in CI (`test_rollback_reapply_and_full_downgrade`): upgrade → downgrade →
upgrade. This used to be broken. Seven PostgreSQL enum types were created by upgrades and
dropped by no downgrade, and `CREATE TYPE` is not idempotent, so the second upgrade failed with
`type already exists`. The affected downgrades now `DROP TYPE IF EXISTS`, guarded on the
dialect.

---

## 6. Backups, and the honest state of them

`run_backup()` **dispatches on the driver**:

* **SQLite** — the app takes the backup itself.
* **PostgreSQL / Aurora** — returns `status="aurora_managed"`, location *"Amazon RDS automated
  backups (PITR + daily snapshots)"*. **The app performs no backup of its own.**

So on Aurora, durability is entirely RDS's: point-in-time recovery plus daily snapshots.
That is a reasonable design — and it means:

> **Nothing has ever been restored.** The RDS side has never been configured and never
> restore-tested. A backup nobody has restored is a hope, not a backup. This is **B3** in
> `FINAL_AUDIT_2026-07-31.md` and it is owner work: enable automated backups, set the
> retention window, then **actually perform a restore into a scratch cluster** and point a
> deployment at it. S4 is the sprint for this.

For logical exports, run `pg_dump` from an ops host — the app does not do it.

---

## 7. Failure recovery

| Symptom | Likely cause | Action |
|---|---|---|
| App exits immediately, `REFUSING TO START` | A boot gate. The message names every problem | Fix the named config. Do **not** set `ENVIRONMENT=development` to silence it |
| `DATABASE_URL has no sslmode` | `?sslmode=require` missing | Add it. Never `disable`/`allow` |
| `/healthz` 503, `db: down` | Cluster unreachable, credentials, or security group | Driver `connect_timeout` is 5 s, so this fails fast rather than hanging. Check the SG first |
| `/readyz` 503, `chunks: 0` | Vector index not built on this instance | The index is **derived** and gitignored. Rebuild: `python -c "from app.ai.vector_store import reseed; reseed(force=True)"`. Expect 15–25 min of CPU embedding |
| `/readyz` 503 only on new instances | Probe timeout too short for a cold start | See the probe note in §3 |
| `chunks` ≠ `expected` | Corpus drift, or a partial reseed | `python -m app.ops.release preflight` will name it. Do **not** `freeze` to make it match — that pins the drift |
| Migration aborts on `tenant_id` NOT NULL | Pre-tenancy data without backfill | §2.4. If half-applied, downgrade to the §1.5 revision and re-run |
| `type ... already exists` on upgrade | An enum from a rolled-back deploy | Should be fixed (§5.3). If it recurs, `DROP TYPE` the named type and re-run |
| **`/docs` is reachable** | `ENVIRONMENT` is not `production` | **Treat as urgent.** There is no separate docs toggle — `main.py` sets `_DOCS_ENABLED = not _is_production()`. Reachable docs prove `_is_production()` is False, so `assert_secrets_sane()` only **warned** about weak secrets and a plaintext `sslmode` instead of refusing to boot. Every fail-closed gate is in warn mode. Set `ENVIRONMENT=production` and redeploy |
| Requests hang under load | Rate limiting is **per-process** | Do not scale horizontally until it is shared (Redis). H2 |
| Aurora paused/stopped | Cluster stopped | The 5 s `connect_timeout` was added after the 2026-06-27 Aurora-stopped incident, so this surfaces as a clean error rather than 30 s hangs |

### `reseed()` is safe to run on a live instance

Build-then-swap by rename, a heartbeating lock (stale after 300 s **by mtime**, never by
`os.kill`), a shrink guard refusing a swap that loses >10% of chunks, orphaned-build adoption
after a crash, and a free-disk floor checked **before** the destructive step. A crash mid-reseed
leaves the old index serving.

---

## 8. What this runbook does not cover

Stated so nobody mistakes its scope:

* **Load and capacity.** The Postgres suite is several times slower than SQLite; that is a test
  observation, not a capacity model. H1.
* **Horizontal scaling.** Blocked on per-process rate limiting. H2.
* **Alerting.** There is no error tracker. A production failure would be silent. H3 / OWNER-12.
* **Restore.** §6 — untested, and the single largest unknown in this document.
