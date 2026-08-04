# Juriscite — Engineering Runbook

Operational reference for building, checking, releasing and recovering Juriscite.
Every command here has been run; where one **cannot** be run in the current environment, that
is stated rather than glossed.

Paths assume the repo root: `D:\MASTER CLAUDE PROJECT FOLDER`. The virtualenv is `venv/`.

---

## 1. Everyday checks

```bash
pytest tests/ -q
```
785 tests, ~8.5 min on SQLite. **Never pipe this into `head`/`tail` before reading the exit
code** — the pipeline's status is the *last* command's, and that mistake once let a release
freeze be committed on a red suite. If you must trim the output, capture `$?` first:

```bash
pytest tests/ -q > /tmp/suite.log 2>&1; echo "EXIT=$?"; tail -5 /tmp/suite.log
```

```bash
ruff check .
```
Repo-wide, rulesets `DTZ` + `F`. Also runs as a **blocking** CI gate and as a pre-push hook.

```bash
pytest tests/test_migrations.py -q
```
Single-head + head-matches-models integrity.

```bash
pip-audit -r requirements.lock $(grep -vE '^\s*#|^\s*$' security/pip-audit-waivers.txt | awk '{print "--ignore-vuln " $1}')
```
Blocking in CI. Waivers are documented, justified vuln IDs — a waiver is for a vulnerability
with **no upstream fix**. If a fix exists, bump the pin instead.

### Hook installation (once per clone)

```bash
pre-commit install
```
`default_install_hook_types` wires **both** `pre-commit` (staged files) and `pre-push`
(`ruff check .` over the whole tree). The pre-push hook exists because staged-file scope is
exactly how the CI lint gate got surprised: violations sat in files nobody had staged.

---

## 2. Database

| | |
|---|---|
| Config | `app/db/config.py` — reads `DATABASE_URL`, defaults to `sqlite:///./legal_server.db` |
| Session | `app/db/session.py` — `get_db()` generator |
| Prod target | PostgreSQL / Aurora, driver `postgresql+psycopg` (psycopg v3) |

`app/security_gate.py` **refuses to boot in production** when `DATABASE_URL` is unset, rather
than silently falling back to local SQLite.

### Migrations

```bash
alembic upgrade head
alembic current
alembic history
```

Compile DDL for a dialect **without a server** — this is how Postgres DDL was verified before
any cluster existed:

```bash
alembic upgrade head --sql
```

> In offline (`--sql`) mode `op.get_bind()` returns `None`. Data migrations must therefore use
> `op.execute("...")` with literal SQL, not a bound connection. The tenancy backfill in
> `530d6dd3a280` is written that way for exactly this reason.

### Running the suite against PostgreSQL

```bash
DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/db" pytest tests/ -v
```

`tests/conftest.py` switches to the real configured engine whenever `DATABASE_URL` is set to
anything non-SQLite. **This cannot be run on the current dev box** — there is no Docker and no
local Postgres server. CI's `test-postgres` job is the only place it executes, which is why
both suites emit JUnit XML uploaded with `if: always()`.

---

## 3. Corpus and vector index

The Chroma index is **derived** from the versioned `app/legal_corpus/fulltext/*.json` and is
gitignored. A clean checkout has no index; the first thing that touches `get_collection()`
builds one (~8,900 chunks, 15–25 min of CPU embedding).

```bash
# list every act in the registry
python -m app.ai.ingest_statutes --list

# parse one act's official PDF into verified full text
python -m app.ai.ingest_statutes <act_id>

# parse every act whose PDF is present in data/source_pdfs/
python -m app.ai.ingest_statutes all

# rebuild the vector index
python -c "from app.ai.vector_store import reseed; reseed(force=True)"
```

Admin HTTP equivalents (firm-admin auth): `POST /api/admin/ingest-statutes`,
`POST /api/admin/reseed-corpus`.

### What `reseed()` guarantees

It is crash-safe by construction — build into a temporary collection, then swap by rename:

* a heartbeating lock file (`RESEED_LOCK_PATH`), stale after 300 s **by mtime**, never by
  `os.kill` (on Windows CPython maps non-CTRL signals to `TerminateProcess`, so a liveness
  probe would kill the process it was probing);
* a shrink guard — refuses a swap that would lose more than 10 % of chunks;
* orphaned-build adoption after a crash;
* a store-scaled free-disk floor, checked **before** the destructive step;
* a frozen corpus snapshot written alongside the index.

Source PDFs (~153 MB) live in `data/source_pdfs/` and are gitignored; their SHA-256 and source
URL are recorded in the versioned fulltext provenance, so integrity stays verifiable without
the blobs.

---

## 4. Release identity

`RELEASE.json` pins the audited release: app version, corpus fingerprint, migration head,
Chroma collection, embedding model, expected chunk count, verified act count, and commit.

```bash
python -m app.ops.release status      # live values, JSON
python -m app.ops.release preflight   # FAILS CLOSED on any drift; exit 1 blocks deploy
python -m app.ops.release freeze      # regenerate RELEASE.json after a verified change
```

Useful flags (local checks only, **never** for a production preflight):
`--no-require-secrets`, `--allow-dirty`.

Preflight verifies the pinned commit is real and in this history, the migration head matches,
the corpus fingerprint matches, the chunk count matches, and required config is present. It
has caught genuine drift twice.

> `test_release_json_pins_a_real_commit_in_this_history` runs
> `git merge-base --is-ancestor <pinned> HEAD`. In a **shallow clone** the pinned object does
> not exist and the test fails — not because the pin is stale but because git cannot see the
> history to judge it. Hence `fetch-depth: 0` on all three CI checkouts.

**Re-freeze after any corpus change**, then re-run the suite. Do not freeze on a red suite.

---

## 5. Boot gates

The app **refuses to start** rather than starting wrong:

| Gate | Location | Enforces |
|---|---|---|
| `assert_secrets_sane()` | `app/security_gate.py` | JWT/field-encryption secrets present and non-weak; unset `ENVIRONMENT` is treated as **production** so forgetting it fails closed |
| `assert_prohibited_disabled()` | `app/legal_config.py` | governance-prohibited features stay off |
| `assert_soul_intact()` | — | integrity of the governing config |
| `_disk_preflight()` | `app/main.py` | warns at boot on low disk; `reseed()` hard-refuses below the floor |

Tests declare `ENVIRONMENT=test` explicitly in `tests/conftest.py` — the gate is never relaxed
on their behalf.

---

## 6. Background jobs

`app/main.py` → `_start_reminder_scheduler()`. APScheduler, daemon thread:

| Job | Schedule |
|---|---|
| `daily_reminders` | 07:00 daily |
| `startup_reminders` | once per boot |
| `daily_backup` | 02:00 daily |
| `weekly_corpus_freshness` | Mon 03:00 — reports only, never auto-ingests |

**The scheduler does not start under `ENVIRONMENT=test`** (override with `SCHEDULER_ENABLED=1`).
It used to, on every one of ~780 `TestClient` boots, doing real work against the real
configured database — and `shutdown(wait=False)` let a job outlive the app and deadlock the
next test on Postgres. Shutdown now waits. See `tests/test_background_scheduler_isolation.py`.

Test jobs by calling `app/services/scheduler.py` and `app/services/notifications.py` directly,
as `tests/test_scheduled_jobs.py` and `tests/test_reminders.py` do.

---

## 7. Backups

`run_backup()` **dispatches on the driver**:

* **SQLite** — the app takes the backup itself.
* **PostgreSQL / Aurora** — returns `status="aurora_managed"`. The app performs no backup of
  its own; durability is RDS point-in-time recovery plus daily snapshots.

> That second path has **never been configured or restore-tested**. A backup nobody has
> restored is a hope, not a backup. Tracked as B3 in `docs/FINAL_AUDIT_2026-07-31.md`.

---

## 8. CI

`.github/workflows/ci.yml` — three jobs, all blocking:

| Job | Does |
|---|---|
| `test` | SBOM, lint gate, migration integrity, full suite on SQLite |
| `test-postgres` | `alembic upgrade head` + full suite against a real `postgres:16` service container |
| `audit` | `pip-audit` against `requirements.lock` with documented waivers |

Both suites upload JUnit XML with `if: always()`, so a failure is machine-readable without
scraping the web UI.

**Install from `requirements.lock`, never `requirements.txt`.** The latter is the *intent*
file and is 23/24 unpinned (`>=` ranges); installing from it makes each run resolve whatever
was newest that day. That is how a suite passes locally and fails in CI for reasons nobody can
reproduce.

Reading a failed run without `gh auth login`: the annotations API returns only
`Process completed with exit code 1`, and the logs API needs an authenticated token. While the
repo is public the rendered log is readable in a browser; once it is private, `gh` auth is
required. Prefer the JUnit artifact.

---

## 9. Standing constraints

These are governance, not preference. They do not get re-litigated in a sprint.

* **Never build** prediction, person-scoring or judge-profiling. Never scrape eCourts.
* Indian Kanoon provides **links only** — never model grounding. `KANOON_ENABLED=false`.
* Judgment corpus is `DEFERRED_BY_GOVERNANCE (C-04)`.
* `BILLING_MODE` stays `test`; live billing is blocked by `assert_billing_mode_allowed`.
* No real client data before gates G6/G7.
* Human gates **G1, G6, G7, G8** and the hallucination sign-off can never be self-certified.
* Never commit `.env`, `*.pem`, local DBs, `data/uploads/`, logs, backups. Never print secret
  values — presence booleans only.
* The AIRA / "Firoz Brain" / soul-constitution governance package was **retired by the owner on
  2026-07-21**. Do not follow it.

---

## 10. Known operational gaps

| Gap | Consequence |
|---|---|
| Rate limiting is **per-process** | Do not scale horizontally until it is shared (Redis). Limits multiply by instance count. |
| Aurora not provisioned | The Postgres path is exercised only in CI, never on the real cluster. |
| No error tracker or alert channel | Failures in production would be silent. Owner picks the tool (OWNER-12). |
| `actions/cache` no longer saves on failed jobs | A persistently-red lane keeps paying the full cold index build. |
