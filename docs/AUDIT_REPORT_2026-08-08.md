# Juriscite — Project & Functional Audit

**Date:** 2026-08-08 · **Branch:** `main` · **HEAD:** `47e02f4` (2026-08-07) · **Commits:** 128
**Python:** 3.14.6 · **App:** 16,106 LOC · **Tests:** 11,558 LOC across 97 files / 866 collected

> **State at time of writing.** The corpus rebuild described in §5.3 has **completed** (50/50
> acts, zero failures) and the regression diff shows **zero unexplained losses**. The working
> tree is uncommitted pending vector-index reseed and `RELEASE.json` re-freeze — until that
> lands, `RELEASE.json` pins a **stale** pre-rebuild fingerprint.

---

## 1. Scope and method

This audit was produced by reading the repository, not by trusting prior documentation. Route
counts come from walking the live FastAPI app; test counts from `pytest --collect-only`;
corpus counts from parsing the shipped `app/legal_corpus/fulltext/*.json`. Where a claim could
not be verified from the repo, it is marked as such rather than asserted.

Two prior audits (`FINAL_AUDIT_2026-07-31.md`, `AUDIT_REPORT_2026-07-20.md`) remain on file.
This one supersedes them on functional inventory and corpus state; it does not re-litigate
their security findings, which are tracked in `docs/SECURITY_REVIEW_PACKAGE.md`.

---

## 2. What the system is

An advocate-first, AI-native legal operating system for India. The product thesis is not
"chatbot over legal PDFs" — it is a practice-management system whose retrieval layer is
grounded in a **curated, provenance-tracked corpus of Indian bare acts**, with deterministic
gates that refuse to answer rather than guess.

The distinguishing asset is the corpus and the machinery that polices it. Most of the
engineering risk in this project is there, not in the CRUD.

---

## 3. Architecture

| Layer | Choice |
|---|---|
| API | FastAPI, 187 endpoints across 22 routers |
| ORM / migrations | SQLAlchemy 2.0 + Alembic (16 migrations) |
| Database | SQLite (dev/test) · PostgreSQL/Aurora (prod target, **not yet provisioned**) |
| Vector store | ChromaDB, ONNX MiniLM embeddings, build-then-swap `reseed()` |
| LLM | Provider-agnostic via `AI_MODEL` + `AI_FALLBACK_MODELS`, with liveness probing |
| Auth | JWT + 2FA; tenant-scoped throughout |
| Frontend | Server-rendered pages + PWA (service worker, manifest, offline shell) |

**LLM provider is deliberately swappable.** `llm_config.py` probes candidate models with a
1-token request (6 s cap) and caches the first responsive one for 10 minutes — a response to a
real incident where a provider listed models it would not actually serve.

---

## 4. Functional feature inventory

Endpoint counts are live, from a recursive walk through FastAPI's `_IncludedRouter` graph.
(A flat `app.routes` scan reports only 40 — worth knowing, because it is how coverage gets
silently overstated.)

### 4.1 Practice management — the operational core

| Module | Endpoints | Function |
|---|---:|---|
| `diary` + `diary_summary` | 19 | Court diary, hearings, deadlines |
| `workbench` | 18 | Advocate workbench; tenant-scoped, every mutation audited |
| `billing` | 9 | Subscriptions, plans, Razorpay webhook |
| `documents` | 8 | Document store with versioning |
| `drafts` | 8 | Saved drafts + advocate review workflow |
| `fees` | 8 | Fees due / collected |
| `cases` / `clients` | 10 | Matter and client records |
| `hearings` | 5 | Hearing scheduling |
| `firm` | 6 | Firm workspace, member management |
| `notifications` | 5 | In-app reminder feed |
| `ecourts` | 3 | **Read-only** eCourts + calendar integration |

### 4.2 AI surface

| Module | Endpoints | Function |
|---|---:|---|
| `ai_chat` | 6 | Legal assistant over the Universal Legal Agent |
| `ai_drafting` | 5 | Drafting engine |
| `research` | 6 | Case-law search + grounded summaries (Indian Kanoon) |
| `library` | 7 | Bare acts + sections, on-demand summaries |

### 4.3 Compliance and governance

| Module | Endpoints | Function |
|---|---:|---|
| `auth` | 14 | Registration, login, 2FA, password reset |
| `account` | 4 | Data-principal rights (DPDP 2023) |
| `data_rights` | 4 | DPDP rights-request tracker |
| `misuse` | 4 | Abuse reporting |
| `admin` | 7 | Administrative operations |
| `audit` | 1 | Audit-log visibility |

---

## 5. The legal corpus

### 5.1 Current state

**50 acts / 9,620 provisions** (rebuild complete, diff verified). Sources are official
India Code PDFs held in `data/source_pdfs/`, with per-act provenance and page numbers so a
cited provision can be checked against the printed page.

The parser is a registry of per-act flags feeding scored segmentation strategies. Candidate
parses are ranked by median body length × coverage, with a page-order tiebreak. This is
unusual and worth defending: it exists because **choosing by section count poisoned the corpus
twice** — a table of contents parses into hundreds of one-line "sections" and wins any count
contest.

### 5.2 Two-level namespaces

Schedules and rules renumber from 1, so without namespacing they overwrite real section
numbers. That collision has cost this project real law more than once. Current namespaces:

- `Sch.<label>.<entry>` — general schedules (Specific Relief, NDPS, Partnership, Mediation)
- `Sch7.L1/L2/L3.*` — Constitution Seventh Schedule legislative lists
- `Ord.<roman>.R.<rule>` — **new, 2026-08-08** — CPC First Schedule

### 5.3 Changes in this cycle (uncommitted)

**CPC First Schedule ingested for the first time — 708 rules across 58 Orders.** Order VII
Rule 11, Order VI Rule 17, Order XXXIX Rules 1–2, Order IX Rule 13 and the whole of Order XXI
(execution) were previously **absent from the corpus entirely**. For a litigation tool that
was a material coverage gap.

Four defects had to be fixed to extract them intact, and two are instructive:

| Defect | Consequence |
|---|---|
| `1[3.` extracted as `13.` | Order X Rule 3 filed as rule 13 — unreachable by its own citation |
| `1[ 21.` matched nothing (space after marker bracket) | Order XX Rule 1 "Judgment when pronounced" absorbed into the heading above it |

**Mediation Act schedules ingested — and three further defects surfaced.** Most notable:
**ss.61 and 62 held the Arbitration Act's substituted text**, pulled in from the Sixth
Schedule, displacing the real amendment sections. Sections 58–60 and 63–65 on either side
were correct. And the bill's **Statement of Objects and Reasons** — a minister-signed
explanatory note, not law — had been ingested as `Sch.X`.

**Indian Succession Act ss.30 and 90 recovered.** `_FOOTNOTE_RE` drops lines whose first word
after the number is an editorial opener (`Subs.`, `Ins.`, `As to`, `Words`). ISA s.30 opens
"**As to** what property deceased considered to have died intestate.—" and s.90 opens
"**Words** describing subject refer to…". Both were deleted before segmentation and absorbed
into ss.29 and 89.

### 5.4 A finding about the audit process itself

The ISA loss **was not introduced by this cycle's work**. It had been live in the parser since
the footnote openers were added; HEAD's committed corpus file simply predated that change and
was never rebuilt. The artifact on disk looked correct while the code producing it did not.

**No test could have caught this**, because every corpus test reads the shipped JSON rather
than reparsing. A full rebuild is the only thing that exposes this class of drift, and one
only happened here because an unrelated change forced it.

> **Recommendation (new, unactioned):** a CI job that reparses the corpus from source PDFs and
> fails if any act's output differs from the committed file. Without it, parser fixes and
> corpus artifacts can silently diverge again.

### 5.5 Known corpus limitations

Tracked in full in `docs/CORPUS_LIMITATIONS.md`. Material open items:

- **Stamp Act ss.8B/8E/8F/23A** — diagnosed, fix known, **deliberately not shipped**
- **BNSS 2023 s.2 (Definitions)** — not retrievable
- **Constitution Schedules 1–6/8/9/11/12** — not ingested; explicitly an **owner + legal** decision
- **IPC 354E** — duplicate section number, pending legal review
- **Companies s.37ZA** — a source-document typo, not a parser defect
- CPC Appendices A–I (pleading forms) and the repealed Second Schedule excluded by design

---

## 6. Safety and governance machinery

These are enforced in code, not policy documents:

| Component | Behaviour |
|---|---|
| `answer_gate.py` | **Fail-closed**: repair-or-withhold, not warn |
| `citation_guard.py` | Deterministic citation resolution; unresolved citation blocks the answer |
| `safety.py` | Banned-phrase screening, confidence assessment, mandatory draft disclaimers |
| `security_gate.py` | **Refuses to boot** on unsafe signing material, non-durable DB, or undeclared upload storage |
| `data_boundary.py` | Log redaction at the AI boundary |
| `privacy.py` | Purpose-scoped consent checked **before every LLM egress** |
| `entitlements.py` | Plan quotas metered and enforced |

**Standing constraints observed in code:** no prediction, person-scoring or judge-profiling;
no eCourts scraping (read-only integration); Indian Kanoon links are **never** model grounding
and require both `KANOON_ENABLED=true` and a key; `BILLING_MODE` defaults to `test`.

---

## 7. Testing and CI

**866 tests** across 97 files. Three CI jobs: `test`, `test-postgres`, `audit` (dependency
audit + secret scan).

The suite is unusually content-oriented for a codebase of this size. Corpus tests assert
**what provisions say**, not how many exist — because a count passes just as happily when
Order XXXIX Rule 1 holds Order XXXVIII Rule 5's text. Several tests exist specifically to
guard the test methodology (`test_the_page_order_metric_is_actually_measuring_something`,
`test_the_enumeration_actually_sees_the_sub_router_routes`).

Verified infrastructure: SQLite/Postgres parity, migration-on-populated-database, endpoint
authorization sweep, LLM egress consent inventory, restore verification, background-scheduler
isolation, uploads durability.

**Not verified:** the suite has not been run to completion since the corpus rebuild began.
The last certified run was 782 passed / 0 failed at fingerprint `a1fecc33d3e0`.

---

## 8. Production readiness — plainly

**This system is not in production and should not be.** What is real:

- ✅ Application code, test suite, CI, migrations, runbooks
- ✅ Backup tooling with a restore verifier that provably detects a database-only restore
- ✅ Boot-time fail-closed gates

What is not:

| Item | Status |
|---|---|
| Aurora / PostgreSQL instance | **Not provisioned** |
| Restore drill against real infrastructure | **Never performed** |
| Human gates G1, G6, G7, G8 | **All BLOCKED_PENDING_HUMAN** — none may be self-certified |
| `BILLING_MODE` | `test` — live payments require G6 + G7 |
| Real client data | **Prohibited** until G6/G7 |
| Client-PII encryption at rest | **Owner decision outstanding** |
| `RELEASE.json` | **Stale** — pins pre-rebuild fingerprint |

---

## 9. Open risks and owner actions

### Requiring owner action

1. **Repository is PUBLIC** (verified via API 2026-08-04/06). The owner asked for it to be
   private; this has not happened. Everything in §5 and §7 is world-readable.
2. **Rotate `INDIAN_KANOON_API_KEY`** — live and per-call billed. Verified never committed,
   but displayed in plaintext in a working transcript.
3. **Client-PII encryption-at-rest** decision.
4. **Erasure-vs-restore policy** — DPDP erasure and backup retention are in tension; needs a
   stated position before real data exists.
5. **Constitution Schedules** — owner + legal, explicitly not an agent decision.
6. **Sign or reject G1/G6/G7/G8.** Nothing downstream can proceed without these.

### Engineering

7. **Corpus-rebuild CI job** (§5.4) — the highest-value new item in this report.
8. Aurora provisioning + a real restore drill.
9. Stamp Act wrapped-heading fix.
10. IT Act 2000 and Legal Services footnote-aware continuation.

---

## 10. Assessment

The engineering discipline here is well above what the feature list suggests. The recurring
pattern in this project's history is that **the dangerous failures are the silent ones** —
provisions that exist, retrieve normally, have plausible length, and are not the law. The
codebase has visibly been shaped by that: fail-closed gates, content-based tests, namespaces
that make collisions impossible rather than unlikely, and comments that record *why* a defect
was invisible rather than just what fixed it.

The corresponding weakness is that verification depth is uneven. Section counts, character
deltas and spot-checks have each, at different times, certified something that was wrong.
§5.4 is the current example: a defect sat in the parser undetected because nothing ever
re-derived the artifact from source.

**The gap to production is not code.** It is provisioned infrastructure, an untested restore
path, four unsigned human gates, and a public repository. Those are decisions and
procurement, not engineering.

---

*Generated 2026-08-08 from repository inspection. Corpus rebuild complete and diff-verified;
`RELEASE.json` requires re-freezing before any release is cut from this state.*
