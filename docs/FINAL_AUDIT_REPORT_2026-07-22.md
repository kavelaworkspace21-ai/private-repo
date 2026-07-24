# Juriscite — Final Audit Report

**Date:** 2026-07-22 · **Version:** 0.2.0 · **Corpus fingerprint:** `2965aab084ff`
**Migration head:** `81665ba86789` (14 migrations) · **Release preflight:** PASSING (prod mode)
**Test suite:** **580 passed / 0 failed** · warnings 2 (both third-party)
**Scale:** 18 pages · 22 routers · **151 API endpoints** · 26 model modules · 71 test files · 29 draft templates
**Root:** `D:\MASTER CLAUDE PROJECT FOLDER`

### How to read this report
`✅ VERIFIED` — exercised in a running app or by tests · `🟡 PARTIAL` — built, not fully proven ·
`🔒 GATED` — needs owner infrastructure or a human signature · `⛔ NOT BUILT`.
Claims here were checked against the running application and source, not carried from earlier notes.

---

# PART 1 — Every page (18)

All pages are server-rendered shells + vanilla-JS modules (no build step), themed "Executive Dark".
**Browser-verified 2026-07-22:** dashboard, assistant, cases, library, drafting, workbench all loaded
with **zero console errors and every API call HTTP 200**.

| # | Page | Route | What it does | Status |
|---|---|---|---|---|
| 1 | **Dashboard** | `/` | Greeting + rotating 3D cube (now bearing the Juriscite logo), KPI tiles (today's hearings, this week, pending tasks, overdue deadlines), 7-day strip, today's hearings / open tasks / upcoming deadlines panels, "Getting started" checklist, monthly-hearings chart (Chart.js, vendored locally) | ✅ VERIFIED |
| 2 | **Sign In** | `/login` | Email+password; issues JWT. Advocates/firm-admins are routed to 2FA setup (skippable) | ✅ VERIFIED |
| 3 | **Register** | `/register` | Creates a user **and its own tenant** (one advocate = one workspace) | ✅ VERIFIED |
| 4 | **2FA Setup** | `/setup-2fa` | TOTP QR + manual secret + 6-digit activation; **"Skip for now"** so it never dead-ends | ✅ VERIFIED |
| 5 | **Reset Password** | `/reset-password` | Token-based reset (email delivery only if SMTP configured) | 🟡 PARTIAL (email unset) |
| 6 | **Consent** | `/consent` | Presents consent items; records acceptance | 🟡 PARTIAL (not enforced at AI boundary) |
| 7 | **Cases** | `/cases` | Matter list + create/edit/delete; the hub linking clients, hearings, documents, fees | ✅ VERIFIED |
| 8 | **Court Diary** | `/diary` | Hearings, tasks, filing deadlines, opposing counsel; today/analytics views; ICS calendar export | ✅ VERIFIED |
| 9 | **AI Assistant** | `/assistant` | Streaming (SSE) legal chat grounded in the verified corpus, with confidence label, citation gate + sources footer; voice input if transcription configured | ✅ VERIFIED |
| 10 | **Drafting Engine** | `/drafting` | Generates draft documents from 29 skeletons; review-gated, disclaimer-stamped; DOCX/PDF export | ✅ VERIFIED |
| 11 | **Workbench** | `/workbench` | Upload a matter file → guided workflows, list-of-dates chronology, artifact generation, save-to-matter, approve | ✅ VERIFIED |
| 12 | **Drafts** | `/drafts` | Saved drafts, version history, revert, approve | ✅ VERIFIED |
| 13 | **Legal Library** | `/library` | Browse the 50-act corpus: acts → sections → verbatim text with provenance; search; corpus-status panel | ✅ VERIFIED |
| 14 | **Firm** | `/firm` | Firm members (add/edit/remove), verification submission | ✅ VERIFIED |
| 15 | **Account** | `/account` | Profile, privacy view, **data export**, **account deletion** (DPDP rights) | 🟡 PARTIAL (propagation unverified) |
| 16 | **Notifications** | `/notifications` | Reminder/notification list, unread count, mark-read | ✅ VERIFIED |
| 17 | **Pricing** | `/pricing` | Plan display (billing in **test mode**) | 🟡 PARTIAL |
| 18 | **Legal Hub** | `/legal`, `/legal/{slug}` | Terms/Privacy/AUP documents | 🟡 PARTIAL (counsel-unsigned drafts) |

**System routes:** `/health`, `/healthz` (liveness: soul + DB), `/readyz` (readiness: vector index),
`/api/admin/status` (protected identity, no secrets), `/manifest.webmanifest`, `/service-worker.js`,
`/offline`, `/favicon.ico`.

---

# PART 2 — Every feature (22 modules, 151 endpoints)

### Practice management (the matter-centric core)
| Module | Endpoints | Function | Status |
|---|---|---|---|
| **clients** | 5 | CRUD for clients (name/email/phone/address), tenant-scoped | ✅ |
| **cases** | 5 | CRUD for matters; parent object that auto-stamps tenant on children | ✅ |
| **hearings** | 5 | CRUD for hearings, linked to cases | ✅ |
| **diary** | 17 | Diary entries, tasks, filing deadlines, opposing counsel — full CRUD each | ✅ |
| **diary_summary** | 4 | Today view, pending tasks, unfiled deadlines, monthly-hearings analytics | ✅ |
| **fees** | 8 | Fees collected + fees due, full CRUD | ✅ |
| **documents** | 8 | Upload (magic-byte validated), metadata, **versioning**, download, delete | ✅ |
| **drafts** | 8 | Saved drafts, versions, revert, **approve** gate, delete | ✅ |
| **notifications** | 5 | List, unread count, mark read/all, run reminders | ✅ |

### AI subsystem
| Module | Endpoints | Function | Status |
|---|---|---|---|
| **ai_chat** | 6 | SSE streaming chat, conversation persistence/list/delete, audio transcription (+status) | ✅ (transcription unset) |
| **ai_drafting** | 5 | Generate/edit/review drafts, list types, export DOCX/PDF | ✅ |
| **workbench** | 18 | Sessions, guided answers, artifact generation, uploads (+chat over upload), list-of-dates, save-to-matter, create-tasks, approve, export | ✅ |
| **research** | 6 | Statute mapping, case search, case summary, latest judgments, provision search, status | 🟡 (uses **paid** Kanoon) |
| **library** | 7 | Corpus status, check-updates, acts, sections, verbatim text, search, section summary | ✅ |

### Identity, tenancy, compliance
| Module | Endpoints | Function | Status |
|---|---|---|---|
| **auth** | 12 | Register, login, 2FA setup/verify, refresh, forgot/reset password, consents, `/me` | ✅ |
| **firm** | 6 | Member management, verification submit/status | ✅ |
| **account** | 4 | Profile, privacy, **export**, **delete account** | 🟡 |
| **data_rights** | 4 | DPDP requests: create, mine, list, update status | 🟡 (correction/grievance/nominee ⛔) |
| **misuse** | 4 | Misuse reports: create, mine, list, update | ✅ |
| **audit** | 1 | Audit log query (auth/admin/data-rights/billing actions) | ✅ |
| **billing** | 9 | Plans, subscription, usage, checkout, seats, cancel/resume, invoices, **Razorpay webhook** | 🔒 test mode only |
| **ecourts** | 4 | ICS calendar export, eCourts status/case lookup/sync (read-only, flagged) | 🟡 dormant |

### Background & operations
- **Scheduler** (`app/services/scheduler.py`): daily reminders (07:00), daily backup (02:00), weekly
  corpus drift (Mon 03:00), startup run. **Durable + idempotent** — a DB `UNIQUE(job_id, slot_key)`
  claim guarantees exactly-once per slot even across multiple workers; every run persists
  start/end/status/detail; `stale_jobs()` detects misses. ✅ VERIFIED (boot-tested)
- **Backups** (`app/services/backup.py`): SQLite online-copy + verify (integrity + core tables) with
  rolling retention; Postgres delegates to RDS-managed. ✅ drill executed
- **Release ops** (`app/ops/release.py`): `status` / `preflight` / `freeze` — fail-closed on stale
  corpus, index mismatch, migration drift, or missing secrets. ✅ VERIFIED

---

# PART 3 — How the AI actually works (end-to-end)

1. **Retrieval is deterministic-first.** A query naming a provision ("Section 138 of the NI Act",
   "Article 21") is resolved by **exact act+section metadata lookup** — no embedding similarity, so
   zero hallucination risk on the most common question type. Act aliases use longest-match; the
   Limitation Act disambiguates "**Article** N" (Schedule) from "**Section** N" (body) by intent.
2. **Semantic retrieval** (ChromaDB, local ONNX MiniLM embeddings) handles everything else.
3. **Prompt assembly** places retrieved statute text inside a delimited source block declared "the
   single source of truth for citations"; injected instructions in that block are contained as data
   (deterministically tested).
4. **Generation** via NVIDIA NIM (`meta/llama-3.1-70b-instruct`) with a liveness-probed fallback chain.
5. **Output gates:** banned-phrase sanitisation → **citation hard-gate** (any citation not in the
   retrieved sources is flagged to the advocate) → **act-aware corpus-integrity signal** (catches
   fabricated/misattributed sections) → repeal/currency banners → confidence label + sources footer.
6. **Refusal doctrine:** no source ⇒ no specific citation; unlawful-purpose screen; drafts stay
   `DRAFT_FOR_ADVOCATE_REVIEW` until a human approves.
7. **Boot gates:** the app **refuses to start** if the safety doctrine or prohibited-feature guard is
   broken (`assert_soul_intact`, `assert_prohibited_disabled`).

---

# PART 4 — Legal corpus

**50 acts · 8,442 provisions · 8,646 embedded chunks · fingerprint `2965aab084ff`.**
Every section carries verbatim text + source URL + SHA-256 + page + fetch date. Ingestion is a
deterministic `pdfplumber` parser — **no LLM anywhere in the corpus pipeline**. Acts are accepted only
after landmark sections verify by *content* keyword.

**Governed limitations** (full detail in `CORPUS_LIMITATIONS.md`):
- **IPC 354E** — the source carries *two different provisions* under one number; the index keeps the
  first and the drop is recorded as a `PENDING_LEGAL_REVIEW` anomaly (not silent).
- **Income-tax Act 1961** — heading-grade, historical use only, repeal-flagged to ITA-2025.
- **Amendment dates are act-level**, not per-provision — date-specific research is unsupported.
- **Constitution Schedules 1-6/8/9/11/12** not ingested.
- **Drift currency** — WAF/landing-page sources report `UNVERIFIED` (never "current") until a human
  records a manual verification.
- **No judgment corpus** — Kanoon results are unverified links, never model grounding.

---

# PART 5 — Security & privacy posture

**Implemented ✅:** bcrypt passwords · TOTP 2FA (`totp_secret` Fernet-encrypted at rest) · JWT ·
per-IP rate limits (login 20/5min, forgot 5/15min, register 10/hr) · security headers + CSP ·
tenant isolation (**cross-tenant IDOR sweep passes** for cases, clients, documents incl. download,
hearings, drafts, fees, diary) · upload hardening (extension allowlist + 20 MB cap +
**magic-byte content sniffing** + tenant-separated storage) · blocking `pip-audit` with documented
waivers · `detect-secrets` baseline · SBOM · prompt log-redaction · fail-closed boot gates.

**Open ⛔ / 🔒:** independent penetration test 🔒 · CSRF review ⛔ · malware scanning ⛔ ·
**consent is NOT enforced at the AI boundary** (model exists, not wired — a real G6 gap) ⛔ ·
deletion/export propagation across DB/files/index/backups/logs unverified ⛔ · KMS/secret-manager,
private DB networking, least-privilege IAM 🔒.

---

# PART 6 — API keys: what we use, and what it costs

### Currently configured
| Key | Service | Status | Cost |
|---|---|---|---|
| `AI_API_KEY` | **NVIDIA NIM** (`integrate.api.nvidia.com`), `meta/llama-3.1-70b-instruct` + 2 fallbacks | ✅ active — powers all AI | **Free developer tier** (credit-based, rate-limited; no per-token bill) |
| `INDIAN_KANOON_API_KEY` | **Indian Kanoon** case-law search | ✅ active | **💰 PAID per use** — the only genuinely billed service |
| `ECOURTS_API_KEY` | eCourts case data | ⚠️ key set but **`ECOURTS_API_BASE` unset → dormant** | Free/gov when enabled |
| `JWT_SECRET` | Internal token signing | ✅ set | Free (not an external API) |
| `FIELD_ENCRYPTION_KEY` | Internal field encryption (Fernet) | ✅ **set 2026-07-22** | Free (not an external API) |

### Deliberately unset (cost = zero)
| Key | Effect |
|---|---|
| `OPENAI_EMBEDDINGS_KEY` | **Embeddings run locally on CPU (ONNX MiniLM) — no API, no cost.** This is the single biggest cost avoidance, since embeddings are the highest-volume AI operation |
| `OPENAI_API_KEY` | OpenAI not used for chat |
| `TRANSCRIBE_API_KEY` | Voice input disabled |
| `RAZORPAY_*` | Payments not configured; `BILLING_MODE` test |
| `SMTP_*` | Email is a safe no-op (reminders show in-app) |

### Cost findings
1. **Indian Kanoon is the only paid API in use.** ⚠️ The **dashboard auto-calls
   `/api/research/latest-judgments` on every page load**, so it bills without anyone searching.
   **Recommended: a `KANOON_ENABLED` flag** so the paid call only fires deliberately.
2. **NVIDIA NIM is free-tier** — sufficient for beta; heavier use would need NVIDIA credits.
3. **AWS:** no AWS SDK (`boto3`) in the app and no AWS credentials configured — the app makes **no
   AWS API calls**. Agent access to EC2 was **revoked 2026-07-22** (20 permission grants removed);
   true key revocation remains an owner action.

---

# PART 7 — Quality & testing

**580 tests passing / 0 failed**, 71 test files. Coverage spans: the deterministic parser + corpus
data pins, corpus drift/currency, retrieval evals (29 high-stakes cases: bail bars, sanction gates,
repeal flags, Limitation disambiguation), safety/refusal (15 cases), citation guard, prompt injection,
cross-tenant IDOR, upload security, scheduler idempotency, release preflight, migrations
(single-head + head-matches-models), backups/restore, billing, consent, health endpoints, PWA.

**CI:** SQLite suite (blocking) · Postgres lane (`alembic upgrade head` blocking; suite advisory
until first green) · ruff DTZ gate · blocking `pip-audit` · CycloneDX SBOM artifact.

**Not covered:** browser end-to-end/a11y/visual-regression, load/soak, failure injection, live-model
adversarial evals.

---

# PART 8 — What is NOT done (honest list)

1. 🔒 **Aurora / production deployment** — cluster not started; prod runs an older corpus.
2. 🔒 **Human gates all unsigned** — G1 (corpus), G6 (privacy), G7 (security), G8 (advocate) + the
   hallucination/citation sign-off. Evidence packs are prepared; signatures are not agent-obtainable.
3. ⛔ **Consent enforcement at the AI boundary** (product decision + code).
4. ⛔ **AI evaluation depth** — claim-to-source *entailment*, expanded advocate-curated eval set.
5. ⛔ **Accessibility/UX/PWA audit** (WCAG 2.2 AA, keyboard, screen-reader, responsive, visual
   regression) — needs a real browser session.
6. ⛔ **Observability & resilience** — metrics/SLOs/alert routing, load tests, failure injection,
   rehearsed rollback.
7. ⛔ **Beta operations** — onboarding, support, feedback loop, willingness-to-pay validation.
8. ⛔ **No version control** — the project is not a git repo (no rollback, no commit pinning).

---

# PART 9 — How long to a production-level platform

**Engineering is no longer the bottleneck.** The critical path is *owner infrastructure* and *human
signatures*, which run on calendar time, not code time. Ranges assume the owner acts promptly and
reviewers are engaged in parallel.

| Phase | Work | Duration | Blocker |
|---|---|---|---|
| **A. Infrastructure** | Start Aurora, prod secrets in a secret manager, DNS/TLS, security groups/IAM, object storage, staging env | **1–2 weeks** | 🔒 **OWNER** |
| **B. Deploy & prove** | Deploy to staging, migrate, restore drill on prod-like infra, smoke tests, rollback rehearsal | **1 week** (after A) | agent |
| **C. Remaining engineering** (parallel with A/B) | Consent enforcement, AI eval expansion + entailment, a11y/UX/PWA audit + fixes, observability/SLOs/alerts, load + failure injection, remaining docs | **3–4 weeks** | agent |
| **D. Human gates** (start now, parallel) | G1 (packet ready — days). G6 privacy + G7 security: engage external reviewers, review, **remediate findings**. G8 senior-advocate session + usability | **4–6 weeks** | 🔒 **HUMAN** — the long pole |
| **E. Closed beta** | 5–10 advocates, synthetic/consented data only, 2-week run + P0 remediation | **3–4 weeks** | 🔒 owner recruits |
| **F. Paid launch prep** | Counsel-approved public pages, Razorpay KYC + live approval, GST/invoicing sign-off, support ownership, SLO evidence, WTP validation | **2–4 weeks** | 🔒 owner + counsel + CA |

### Realistic totals
- **Supervised closed beta (real advocates, synthetic data): ~6–9 weeks** — gated on Aurora + G1/G8;
  G6/G7 must be signed before *any real client data*.
- **Production with real client data: ~10–14 weeks** — requires G6 + G7 signed and their findings
  remediated.
- **Public paid launch: ~4–5 months** — adds beta remediation, live billing, support, SLO evidence,
  and willingness-to-pay validation.

**What compresses this:** starting the human-gate engagements **now, in parallel** (they're the long
pole and don't depend on remaining code), and starting Aurora this week.
**What blows it out:** serial scheduling of gates, a pentest finding structural issues, or waiting for
engineering before booking reviewers.

**Caveat:** these are engineering-informed estimates, not commitments — the durations for external
reviews, counsel, KYC, and advocate recruitment are outside anyone here's control.

---

# PART 10 — Owner action list (in priority order)

1. **Start the Aurora cluster** + put `DATABASE_URL`/`FIELD_ENCRYPTION_KEY` in a secret manager (the
   local dev key is set; production needs its own, separate key). ← *unblocks everything downstream*
2. **Book G6 (privacy counsel) and G7 (external pentest) now** — the long pole; evidence packs are ready.
3. **Sign G1** (corpus authenticity packet has been ready and unsigned since 2026-07-20).
4. **Schedule the G8 senior-advocate session** (behaviour + templates + usability).
5. **Decide the consent-enforcement policy** (should AI be blocked without consent in beta?).
6. **Add a `KANOON_ENABLED` guard** (or authorise me to) — stop the paid API auto-firing on dashboard load.
7. **`git init`** — there is currently no version control, so no rollback or commit pinning.
8. **Rotate the EC2 key pair** if you want my revoked access to be truly irreversible.
9. Confirm GST/SAC with a CA and Razorpay KYC before any live billing.

---

**Bottom line.** Juriscite 0.2.0 is a genuinely complete, well-tested advocate platform: 151
endpoints across 18 pages, a 50-act source-verified legal corpus with deterministic-first retrieval
and layered anti-hallucination gates, hardened multi-tenant security, durable operations, and a
reproducible fail-closed release process — **580 tests green**. It is **not production-ready**, and
should not be represented as such: production requires infrastructure that does not yet exist and
four human signatures that cannot be self-certified. The engineering runway to those gates is clear,
documented, and largely complete.

*Prepared by the build system, 2026-07-22. This report describes and measures; the human gates decide.*
