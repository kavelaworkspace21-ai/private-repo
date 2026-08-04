# CI Release Evidence — S1

**Repository:** `kavelaworkspace21-ai/private-repo` · **Branch:** `main`
**Recorded:** 2026-08-04 · **Sprint:** S1 — CI GREEN, FOR REAL

This is the evidence artifact required by S1. It records the run IDs, commit SHAs and
outcomes that back each acceptance criterion — including the run that was deliberately made
to fail, because a gate nobody has watched fail is not known to work.

---

## 1. The green run

| | |
|---|---|
| **Run** | [#21 — 30910900786](https://github.com/kavelaworkspace21-ai/private-repo/actions/runs/30910900786) |
| **Commit** | `1cc5ffb` — *S2: fix the index-plan test — it was asserting something false* |
| **Conclusion** | **success** — all three jobs |

| Job | Result | Duration |
|---|---|---|
| `test` (SQLite) | success | 6.3 min |
| `test-postgres` (real `postgres:16`) | success | 6.5 min |
| `audit` (pip-audit, blocking) | success | 0.5 min |

Earlier green baselines: **#12** (`0d0fac9`) was the first all-green run; **#15** (`e4a6ee6`)
added the broadened lint gate. #21 is current and additionally carries the S2 parity and
populated-migration suites.

The first all-green run was **[#12 — 30884080213](https://github.com/kavelaworkspace21-ai/private-repo/actions/runs/30884080213)** at commit `0d0fac9`
(`test` 5.8 min, `test-postgres` 5.7 min, `audit` 0.6 min). Run #15 is the current baseline
and additionally carries the broadened lint gate.

## 2. Acceptance criteria

| Criterion | Evidence |
|---|---|
| CI is green on a clean commit | Run #15, commit `e4a6ee6`, all jobs success |
| SQLite suite passes | `test` job → step *Full test suite (SQLite)*, 785 tests |
| PostgreSQL suite passes | `test-postgres` job → step *Full test suite (Postgres)* against a `postgres:16` service container |
| Migration checks pass | `test` job → step *Migration integrity (single head + head matches models)*; `test-postgres` job → step *Alembic upgrade head* against real Postgres |
| Lint passes | `test` job → step *Lint — datetime-zone regression gate (BLOCKING)*, `ruff check .` with `select = ["DTZ", "F"]` |
| Release identity checks pass | `tests/test_release_ops.py` runs inside both suites; `test_release_json_pins_a_real_commit_in_this_history` needs full history, hence `fetch-depth: 0` on all three checkouts |
| A deliberately broken test proves the lane fails | §3 below |

## 3. The negative control — proof the lane fails when it should

Every gate had already been seen failing on a *real* defect: the lint gate on run #1, the
SQLite suite on #1–#5, the Postgres suite on #10, the dependency audit on #11. None of those
prove that a **plain failing assertion** fails the build, because each failed for some other
reason — a lint rule, a missing git object, a fixture deadlock, a CVE feed. A suite that
collects zero tests is also green.

So one was run deliberately. `tests/test_ci_negative_control.py` added two failing tests: one
with no fixtures at all, one through the `client` fixture so the Postgres lane exercised its
own path.

| Run | Commit | `test` | `test-postgres` | `audit` |
|---|---|---|---|---|
| [**#13** — 30884637089](https://github.com/kavelaworkspace21-ai/private-repo/actions/runs/30884637089) — broken | `a87299e` | **failure** | **failure** | success |
| [**#14** — 30884659206](https://github.com/kavelaworkspace21-ai/private-repo/actions/runs/30884659206) — reverted | `4cb2218` | success | success | success |

Run #13 failed at exactly the expected steps — *Full test suite (SQLite)* and *Full test
suite (Postgres)* — and `audit` stayed green, correctly, because it runs no tests. Run #14 is
the revert, green again. This proves collection, assertion and exit-code propagation end to
end on both database lanes.

The broken commit was reverted in the commit immediately following it; `main` was red for
under a minute and no run in between was skipped or cancelled.

## 4. What was actually wrong, and what fixed it

CI had never executed before 2026-07-31 — there was no git remote, so S0.4 recorded intent
rather than an outcome. Fifteen runs later:

| Run | Failure | Root cause | Fix |
|---|---|---|---|
| #1 | lint gate | 2 DTZ violations in unstaged files | `6326422` |
| #2 | migration integrity | CI installed unpinned deps, not `requirements.lock` | `bcbe140` |
| #1–#5 | SQLite suite | `actions/checkout` shallow clone — the release-pin test could not see history to judge it | `0c1aca3` |
| #4, #5, #7, #9 | postgres **cancelled** at 45/90/90/90 min | schema DDL per test (~40 tables × 3 × 780) | `050f8ed` |
| #10 | postgres **failed** at 8.1 min | lock contention, now named instead of hanging | `71d42d8` |
| #10 | 17 fixture errors | background scheduler outliving the app; leaked sessions | `2a9e12c` |
| #11 | audit | two CVEs published against the locked set | `0d0fac9` |

### The finding worth keeping

Run #10 returned **764 passed, 1 skipped, 17 errors** — and *every* error was in `client`
fixture setup. **No test logic failed on PostgreSQL.** There were no SQLite-only test
assumptions left to fix; the harness itself was the defect, in two independent ways:

1. **The background scheduler.** `lifespan` started an APScheduler `BackgroundScheduler` on
   every `with TestClient(app)` — ~780 times per run — and `_startup_reminders_job` fires
   immediately on each boot. That job is real work against the *real* configured database: it
   calls `next(get_db())` rather than the test's dependency override, INSERTs a
   `scheduled_job_runs` row, purges read notifications and deletes expired workbench uploads.
   Locally, with `DATABASE_URL` unset, that database is the developer's own
   `legal_server.db`. Shutdown was `shutdown(wait=False)`, which returns without waiting — so
   the job ran on into the next test.
2. **Sixteen leaked sessions** across ten test files doing
   `db = next(app.dependency_overrides[get_db]())`. `next()` advances the generator to its
   `yield` and abandons it, so `finally: db.close()` never runs and the backend sits
   `idle in transaction` holding `AccessShareLock`.

`TRUNCATE` needs `ACCESS EXCLUSIVE` on all 33 tables, so either one deadlocks it. **None of
this is visible on SQLite**: every test gets a fresh temp database file, and the orphaned job
writes to the previous one, already deleted. The suite was green for exactly as long as
nobody ran it against a database that takes locks.

Fixing it made the Postgres lane *faster than SQLite* (5.1 min vs 5.4 min), because 780
spurious scheduler boots and their startup jobs went away.

## 4a. S2 additions, and how a red run is now read

Runs #18–#21 added the S2 suites and produced seven, then one, then zero failures — **every
one of them a defect in the new tests rather than in the app**. Recorded because a red parity
lane is not automatically evidence of a parity bug:

| Run | Result | Cause |
|---|---|---|
| #18 | 7 failed | `str(URL)` redacts the password as `***`; a misspelled column (`filepath`/`file_path`); raw SQL bypassing a model-level default |
| #20 | 1 failed | the index test asserted an index scan against a query matching **half** the table — PostgreSQL's `Seq Scan` was correct |
| #21 | **green** | — |

### Reading a failure without a login

Both machine-readable routes into a run are shut without an authenticated token: the **logs**
API and the **artifact download** API both return 401/403, verified on this public repo. The
check-run **annotations** API is readable unauthenticated — but a failing `run:` step produces
exactly one annotation, `Process completed with exit code 1`, and pytest emits none of its own.
So diagnosing runs #10 and #18 meant scraping thousands of lines of rendered HTML out of the
Actions web UI in a browser.

`.github/scripts/annotate_junit.py` now converts the JUnit XML into one annotation per failing
test, `if: failure()`. It paid for itself on the next run: the single remaining failure came
back from one unauthenticated API call, complete with the assertion message and the query plan.

It cannot change a result — it only reports what the XML already says, and the suite step's own
exit code is what fails the job.

## 5. Gates NOT weakened

S1's critical rule: no `|| true`, swallowed exit codes, relaxed assertions, skipped tests or
reduced coverage to obtain green. For the record, this sprint moved every dial the other way:

* `continue-on-error: true` **removed** from the Postgres suite step — it is now blocking.
* Ruff broadened from `DTZ` to `DTZ` + `F`; 38 violations fixed rather than ignored.
* Lint enforcement extended from staged files to the whole tree at push time.
* Two CVEs **patched**, not waived — a waiver is for a vulnerability with no fix available,
  and both had one.
* Test count went **up**, 782 → 785 (`tests/test_background_scheduler_isolation.py`).
* `save-always: true` removed from both cache steps: GitHub deprecated it, so it read as a
  solved problem while doing nothing.

The two pre-existing pip-audit waivers in `security/pip-audit-waivers.txt` are unchanged and
still carry written justification (`ecdsa` — unused, JWTs are HS256; `chromadb` — ingests only
our own verified corpus).

## 6. Reproducing this locally

```bash
pytest tests/ -q                 # 785 passed  (~8.5 min, SQLite)
ruff check .                     # repo-wide, DTZ + F
pytest tests/test_migrations.py -q
pip-audit -r requirements.lock $(grep -vE '^\s*#|^\s*$' security/pip-audit-waivers.txt | awk '{print "--ignore-vuln " $1}')
```

The **Postgres lane cannot be reproduced on the current dev box** — there is no Docker and no
local Postgres server. CI is the only place it runs, which is why both suites now emit JUnit
XML uploaded with `if: always()`: diagnosing run #10 otherwise meant scraping 5,000 lines of
rendered HTML out of the Actions web UI, because the annotations API returns only
`Process completed with exit code 1` and the logs API requires an authenticated token.

**Environment:** Python 3.12 in CI (3.14.6 locally), dependencies installed from
`requirements.lock` in every job.

---

## 7. Open items

* **The repository is still PUBLIC** (verified against the API on 2026-08-04:
  `visibility: public`). It was made public so CI logs could be read without auth; setting it
  back to private is `OWNER-13` in `docs/OWNER_QUEUE.md`. Note that doing so makes Actions
  logs unreadable without `gh auth login`.
* `actions/cache` no longer saves on a failed job — `save-always` was removed as deprecated
  and its documented replacement (`actions/cache/restore` + `actions/cache/save` with
  `if: always()`) is not yet wired. Consequence: a persistently-failing lane keeps paying the
  full cold vector-index build. Tracked in `docs/OWNER_QUEUE.md`.
* Green is proven on `main` only. No pull-request run has exercised the `pull_request`
  trigger yet.
