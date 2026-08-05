# Juriscite — Final Audit & Path to Release

> **SUPERSEDED IN PART — 2026-08-04.** This is a dated snapshot and is left as written rather
> than edited, so the record of what was known on 2026-07-31 stays intact. Two things below
> have since changed:
>
> * **§1 "CI — not yet green" and §4 B1 "Get CI green" are DONE.** All three jobs pass on
>   `main`; the Postgres suite runs against a real `postgres:16` and is blocking. Run IDs,
>   commit SHAs and the deliberately-broken-test negative control are recorded in
>   [`CI_RELEASE_EVIDENCE.md`](CI_RELEASE_EVIDENCE.md). §3's table of seven runs is superseded
>   by the fuller table there.
> * **§4 B8 "Set the repo private" is still OPEN**, and was verified still open on 2026-08-04
>   (`visibility: public`). Tracked as OWNER-13 in [`OWNER_QUEUE.md`](OWNER_QUEUE.md).
>
> **§5's first risk has materialised.** "Corpus contains wrong law in an unexamined act —
> Medium / Severe" was rated a risk; on 2026-08-04 (S6) it was confirmed as fact. **Ten
> provisions across five acts contain text that is not the law** — including CPC s.9
> (jurisdiction of civil courts), CPC s.2 (Definitions), Companies Act s.3 (formation of a
> company) and Constitution Art 2. None contains amending language, so the scanner built after
> the July finding could not see them, and every other check only asked whether a
> section-shaped chunk existed. Detection is now in place and pinned; recovery is S7. Tracked
> as OWNER-15, **blocking for G1**. See [`CORPUS_LIMITATIONS.md`](CORPUS_LIMITATIONS.md).
>
> Everything else — the corpus findings in §2, the rest of the risk register in §5, and
> blocking items B2–B7 — stands as written, **except that §5's "Backup unrestorable — Unknown / Severe" row
> is now worse than Unknown.** S4 (2026-08-04) established that uploaded client files have no
> backup at all: document rows are in PostgreSQL and covered by Aurora PITR, but the bytes are
> on local disk under `data/uploads/`, and `app/services/storage.py` is filesystem-only. This
> is not an untested backup, it is the absence of one. Tracked as OWNER-14; see
> [`BACKUP_AND_DR.md`](BACKUP_AND_DR.md) §1.

**Date:** 2026-07-31 · **HEAD:** `0c1aca3` · **App version:** 0.2.0
**Corpus fingerprint:** `a1fecc33d3e0` · **Index:** 8,914 chunks · **Commits:** 88

> Scope note. This audits what is **verifiable from the repository**: code, corpus, tests,
> CI. It does not and cannot certify legal accuracy, product-market fit, or regulatory
> compliance — those need a qualified human, and several are formal gates below.

---

## 1. Where the app actually is

| Dimension | Status |
|---|---|
| Test suite | **782 passed / 0 failed** locally (SQLite), 87 test files |
| Corpus | 50 acts, 8,710 sections + schedule entries |
| Vector index | 8,914 chunks, fingerprint-pinned, atomically rebuilt |
| Release identity | `RELEASE.json` + `preflight` fail-closed on drift |
| CI | Runs for the first time as of 2026-07-31; **not yet green** |
| Database | SQLite (dev/test). **PostgreSQL/Aurora never exercised end-to-end** |
| Deployment | Not deployed. Aurora not provisioned |
| Billing | `BILLING_MODE=test`, live billing blocked by `assert_billing_mode_allowed` |

**Honest one-line summary:** the application is functionally built and internally
consistent, its legal corpus is in materially better shape than a week ago, and it has
never been deployed, never run against its production database, and never been reviewed by
a lawyer.

### What is genuinely solid

* **Fail-closed boot gates** — `assert_secrets_sane()`, `assert_prohibited_disabled()`,
  `assert_soul_intact()`. A misconfigured deploy refuses to start rather than starting
  wrong.
* **The citation gate withholds.** `validate_answer()` removes sentences carrying
  unverifiable citations, and withholds the answer entirely if too little survives. It does
  not merely warn.
* **Consent is enforced at the AI boundary**, with withdrawal, and every LLM egress point
  is behind it.
* **Tenant isolation** has a cross-tenant IDOR sweep in the suite.
* **Release identity is reproducible.** `preflight` refuses to deploy a tree that is not
  the audited one — and it caught real drift twice during this session.
* **`reseed()` is now crash-safe**: build-then-swap by rename, a heartbeating lock, a
  shrink guard, orphan adoption, a store-scaled disk floor, and a frozen corpus snapshot.

### What is fragile or unproven

* **CI has never gone green.** Seven runs, each surfacing a real defect. See §3.
* **Postgres is untested in anger.** Migrations compile and apply; the suite has never
  completed against it.
* **Backups on Aurora are RDS-managed, by design** — but that means the app performs no
  backup of its own there, and the RDS side has never been configured or restore-tested.
* **The corpus is right where it has been checked, and unchecked elsewhere.** 50 acts; this
  session examined perhaps 20 closely.

---

## 2. The corpus: what changed and what remains wrong

### Fixed this session

**Ten sections across three acts held AMENDING legislation instead of law** — nine of them
wrong since before version control. India Code prints the amending Act in the same PDF; its
clauses renumber from 1 and overwrite the principal Act's sections. The provisions existed,
had plausible length, and retrieved normally. They simply were not the law.

| Act | Sections | Now |
|---|---|---|
| `arbitration_1996` | 6, 16, 18 | s.16 is competence-competence again |
| `crpc_1973` | 16, 38, 44 | Metropolitan Magistrates; Arrest by Magistrate |
| `ibc_2016` | 6, 19, 26, 36 | who may initiate a CIRP; Liquidation estate |

**Fifteen acts gained provisions that were absent entirely**, including whole regimes: IBC
ss.54B/54E/54F (2021 pre-packaged insolvency), IBC s.9 (operational-creditor CIRP), Stamp
Act s.2 Definitions (11,191 ch), Motor Vehicles s.2 + 33 more, Constitution Arts.
124C/131A/242/272/306, Hindu Succession s.14, Transfer of Property s.58 and s.43.

**120 schedule entries recovered** — NDPS's psychotropic list, the Specific Relief
infrastructure categories that define "infrastructure project" for s.20A, Partnership
Schedule I fees. Namespaced `Sch.*` so a schedule entry can never occupy a section number.

**Four candidates rejected on evidence**, not applied: `it_act_2000`, `legal_services_1987`,
the `arbitration_1996` flags, and `ipc_1860 +wrapped_headings`.

### Known-wrong, recorded, NOT fixed

| Item | Impact | Fix needed |
|---|---|---|
| Stamp ss.8B/8E/8F/23A unaddressable | text merges into 8A/8D/23; found semantically, not by number | 8-series suffix handling |
| `it_act_2000` | recovers 9 sections but destroys 8,399 ch of Definitions | footnote-aware continuation |
| `legal_services_1987` | recovering ss.8/11 cuts s.2(j), (k), s.2(2) | same |
| Mediation ss.49, 55 | absent; recovering them costs s.64 and s.65 | parser work |
| Constitution Schedules 1–6, 8, 9, 11, 12 | not ingested | owner + legal decision |
| IPC 354E | duplicate section number, two distinct provisions | `PENDING_LEGAL_REVIEW` |
| ToP repeal notices (ss.86–88, 96, 98, 135) | searching a repealed section returns nothing | minor, accepted |

### The finding that outlives this session

Every integrity check the project had asked *is the section present?* — counts, coverage,
fingerprints, the citation gate. **None asked whether the text is law.** A corpus can be
complete, reproducible, fingerprinted and fully covered while a section quietly says
something else. `tests/test_corpus_contamination.py` now asks that question; expected count
is zero.

A related caution, learned in both directions: this project has been wrong about corpus
content when believing text was present that was amending legislation, **and** when
believing text was missing that was there all along (Order XV-A). A claim about the corpus
is a claim to verify, not inherit.

---

## 3. CI — seven runs, seven findings

CI had never executed before today. There was no git remote; S0.4 recorded intent, not an
outcome. Every run surfaced something real:

| Run | Failure | Root cause | Status |
|---|---|---|---|
| #1 | lint gate | 2 DTZ violations | fixed `6326422` |
| #2 | migration integrity | CI installed unpinned deps, not `requirements.lock` | fixed `bcbe140` |
| #3 | SQLite suite | *(the shallow clone, misdiagnosed)* | — |
| #4 | postgres cancelled 45m | schema DDL per test | — |
| #5 | postgres cancelled 90m | same; timeout was the wrong lever | fixed `050f8ed` |
| #6/#7 | in flight | — | — |
| all | SQLite suite | **`actions/checkout` shallow clone** — the release-pin test could not see history | fixed `0c1aca3` |

**`Alembic upgrade head` has passed against real PostgreSQL 16 in every run.** That is the
strongest single result: the tenancy migration fix is validated on a real server.

### Two Postgres deploy hazards found and fixed

1. **The tenancy migration could not be applied to a database with data.** `tenant_id` was
   added `NOT NULL`, no default, no backfill, to populated tables. **CI could not catch this
   by construction** — it starts from an empty database, where the add always succeeds. The
   lane would have gone green on precisely the migration that breaks a populated Aurora.
2. **A rolled-back deploy could not be re-applied.** Seven enum types created, none dropped;
   `CREATE TYPE` is not idempotent.

---

## 4. Pending actions to reach release

### BLOCKING — cannot ship without these

| # | Action | Owner | Why |
|---|---|---|---|
| B1 | **Get CI green** — both suites, both databases | agent | Nothing else is trustworthy until the pipeline passes once |
| B2 | **Provision Aurora, run migrations against it** | owner (AWS) | Agent AWS access revoked. Migrations compile and apply in CI; the real cluster is untested |
| B3 | **Restore-test the RDS backup path** | owner | Backups on Postgres are RDS-managed. Never configured, never restored. A backup nobody has restored is a hope |
| B4 | **Rotate `INDIAN_KANOON_API_KEY`** | owner | Live, per-call billed. Never committed (verified across all 88 commits) but displayed in plaintext in a working transcript |
| B5 | **Human gate G1** — corpus authenticity sign-off | owner + lawyer | Never self-certifiable. §2 lists exactly what is known-wrong |
| B6 | **Human gates G6/G7** — security & privacy review | owner | Gate live billing and real client data |
| B7 | **Hallucination sign-off** | owner + lawyer | The citation gate is mechanical; whether outputs are *safe for an advocate to rely on* is a human judgement |
| B8 | **Set the repo private** | owner | Currently public. Contains `THREAT_MODEL.md`, the Postgres hazard audit, and the known-defect list |

### HIGH — should not ship without, but not strictly blocking

| # | Action | Owner |
|---|---|---|
| H1 | Load-test the Postgres path; the suite is 10× slower there than SQLite | agent |
| H2 | Rate limiting is per-process — **do not scale horizontally** until it is shared (Redis) | agent |
| H3 | Error tracker + alert channel (GlitchTip/Sentry, email/Slack) | owner picks, agent wires |
| H4 | Corpus drift monitor — detect when a source PDF changes upstream | agent |
| H5 | Decide Constitution Schedules 1–6/8/9/11/12: ingest or document the gap in-product | owner |

### MEDIUM — quality and maintainability

| # | Action |
|---|---|
| M1 | Parser work: footnote-aware continuation (IT Act, Legal Services), Stamp 8-series suffixes |
| M2 | Mediation ss.49/55 recovery without losing s.64/s.65 |
| M3 | `STATUS.md` is 2,100+ lines; fold resolved entries into a summary |
| M4 | Widen `test_corpus_contamination` patterns as new acts are added |
| M5 | Pre-commit hook running `ruff check .` repo-wide — the DTZ failure escaped because local runs were file-scoped |

### DEFERRED BY GOVERNANCE — do not build

* Prediction, person-scoring, judge-profiling — **never**
* eCourts scraping — **never**
* Kanoon links as model grounding — **never** (links only, `KANOON_ENABLED=false` default)
* Judgment corpus — `DEFERRED_BY_GOVERNANCE (C-04)`

---

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Corpus contains wrong law in an unexamined act | **Medium** | **Severe** — an advocate files on it | Contamination scanner; G1 review; §2 disclosure |
| Aurora deploy fails on first migration | Low | High | Compile-verified + CI-applied; B2 removes it |
| Postgres runtime behaviour differs from SQLite | **Medium** | High | B1 closes it |
| Backup unrestorable | Unknown | **Severe** | B3 — currently untested |
| Rate limits bypassed by scaling out | Low now | Medium | H2 before any horizontal scale |
| Stale release pin deployed | Low | Medium | `preflight` fails closed (caught it twice) |

---

## 6. Recommended order

1. **B1** — CI green. Everything else is guesswork until the pipeline passes once.
2. **B8** — repo private. Costs nothing, open exposure now.
3. **B4** — rotate the Kanoon key. Outstanding for days.
4. **B2 + B3** — Aurora provisioned, migrated, and a restore actually performed.
5. **H2, H3** — rate limiting and alerting before any real traffic.
6. **B5, B6, B7** — the human gates, with §2 in front of the reviewer.

Nothing in 4–6 is agent-completable. B1 is in progress; H1/H4 and all of §M are.

---

## 7. The through-line

Nearly every defect found today was a **check that reported nothing**: a content probe that
raised instead of asserting; a suite whose exit code was swallowed by `tail`, letting a
freeze commit on a red run; a status check matching a sentinel the chain had echoed; a CI
gate configured so it could not fail; a lockfile nothing consumed; and a test that passed
*because* the corpus was corrupt.

The corpus damage was real and years old. It survived because the things watching it were
not looking.

The question worth asking of any check before trusting it: **what would make this fail, and
has it ever?**
