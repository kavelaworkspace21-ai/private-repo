# Juriscite — Final Audit Report

**Date:** 2026-07-20 · **App version:** 0.2.0 · **Corpus fingerprint:** `2965aab084ff`
**Test certification:** 511 passed / 0 failed (full suite, this date)
**Scope:** complete project knowledge + current tech stack, verified against the live repo (not from memory).

---

## 1. What Juriscite is

A multi-tenant SaaS legal practice platform for Indian advocates — "India's Legal Operating
System" (FastAPI title). It combines practice management (clients, cases, hearings, diary,
fees, documents, notifications) with a **source-verified statutory research and drafting AI**
whose defining property is *corpus discipline*: every statutory quote traces to an official
government PDF by SHA-256, page number, and fetch date, and the model is forbidden from
inventing legal text.

**Governance chain of authority:** `docs/governance/` constitution → `CLAUDE.md` → `docs/STATUS.md`
(canonical status mirror, repo-verified).

Two hard-wired, fail-closed boot gates in `app/main.py`:
- `app/legal_config.py::assert_prohibited_disabled()` — prohibited AI features can never be enabled (LSAI-LEGAL-09).
- `app/soul.py::assert_soul_intact()` — the app **refuses to boot** if the safety doctrine is broken, disabled, or tampered with ("THE SOUL", `docs/governance/SOUL_HARDWIRED_CONSTITUTION.md`).

---

## 2. Tech stack

### Backend
| Layer | Technology |
|---|---|
| Language / runtime | Python 3.12 (venv local; `python:3.12-slim` in Docker) |
| Web framework | FastAPI ≥ 0.137 + Uvicorn (standard) |
| ORM / migrations | SQLAlchemy 2.0 + Alembic (14 migration versions) |
| Databases | SQLite (`legal_server.db`, local dev/demo) · PostgreSQL/Aurora via `psycopg[binary]` (production; `schema_postgres.sql`) |
| Auth | JWT (`python-jose`), bcrypt 4.0.1 via passlib, TOTP 2FA (`pyotp` + `qrcode`) |
| Field encryption at rest | `cryptography` ≥ 43 (`app/db/crypto.py`, `FIELD_ENCRYPTION_KEY`) |
| Scheduling | APScheduler (in-process BackgroundScheduler) |
| Docs / PDF | `python-docx`, `reportlab` (generation) · `pdfplumber` (deterministic statute extraction) |
| Payments | Razorpay (keys + webhook secret; `BILLING_MODE` + `BILLING_LIVE_APPROVED` human gate) |
| Container | Dockerfile (python:3.12-slim + libgomp1 for onnxruntime/chromadb), docker-compose, `deploy/deploy_ec2.sh` |

### AI stack
| Component | Technology |
|---|---|
| LLM gateway | OpenAI-compatible client (`openai` ≥ 1.54) against **NVIDIA NIM** (`AI_BASE_URL`) |
| Primary model | `meta/llama-3.1-70b-instruct` (owner-switched 2026-07-15) |
| Failover | `AI_FALLBACK_MODELS` chain (3.3-70b, 3.1-8b) — 1-token 6 s liveness probe, first responsive model wins, cached 10 min (`app/ai/llm_config.py`) |
| Local fallback | Ollama models on-box (`~/.ollama`, ollama/ dir) |
| Vector store | ChromaDB ≥ 0.5 (PersistentClient, sqlite-backed) — collection `indian_law_sections`, **8,646 chunks**, default ONNX MiniLM embeddings |
| Retrieval | `app/ai/rag.py` — deterministic section lookup first (act-alias longest-match + exact `act_title`+`section` metadata get, incl. the `Sch.N` Schedule-article namespace), semantic search second |
| Transcription | Whisper-large-v3 via `TRANSCRIBE_*` config (voice features gated on provider audio support) |
| Case law | Indian Kanoon live search (read-only links, marked "good-law status unverified"; e-SCR ingestion = owner decision C-04) |

### Frontend
- **Vanilla JS progressive web app** served from `app/static/` — no framework, no build step: `app.js`, per-feature modules (`cases.js`, `diary.js`, `drafting.js`, `workbench.js`, `assistant.js`, `library.js`, `firm.js`), `service-worker.js` + `manifest.webmanifest` + `offline.html` (installable PWA).
- Chart.js **vendored locally** (`chart.umd.min.js`) after a CDN single-point-of-failure killed the dashboard (2026-07-15 incident); all chart calls guarded/try-caught.
- **Mobile:** Capacitor wrapper in `mobile/` (capacitor.config.json + www/).

### Storage layout (owner-directed, 2026-07-20)
- Corpus of record (versioned, in-repo): `app/legal_corpus/fulltext/*.fulltext.json`.
- Derived/heavy data on **D:** — `D:\Juriscite\chroma_db` (386 MB) + `D:\Juriscite\source_pdfs`, wired by `CHROMA_PATH` / `SOURCE_PDF_DIR` in `.env` (env-first, in-repo defaults for EC2/CI — keep vars unset there). Also `D:\Juriscite\{backups,corpus,artifacts}`.
- **EC2 deploys must now package chroma_db from D:, not the repo root.**

---

## 3. Application surface

**22 routers** (`app/routers/`): auth · account · clients · cases · documents · hearings · fees · diary · diary_summary · drafts · ai_chat · ai_drafting · research · library · ecourts · notifications · audit · firm · data_rights · misuse · billing · workbench.

**25 SQLAlchemy model modules** (`app/models/`): tenant, user, client, case, hearing, document (+versions), diary entry/task, filing_deadline, fee_due/fee_collected, generated_draft, draft_version, ai_chat, audit, backup_run, billing, consent, data_rights, misuse_report, notification, opposing_counsel, user_activity, workbench.

**Services** (`app/services/`): backup, billing, calendar_export, draft_templates (28 skeletons, G8-gated), email, entitlements, library, mapping.

**Integrations** (`app/integrations/`): eCourts API client. Indian Kanoon via `app/ai/case_law.py`.

**Scheduled jobs** (APScheduler, in `app/main.py`): daily hearing/deadline reminders (07:00 + on boot), daily encrypted backup (02:00, `BACKUP_DIR`/`BACKUP_KEEP`), **weekly corpus drift check** (Mon 03:00 — re-downloads official PDFs, SHA-256 compare, reports and never auto-ingests).

**AI subsystem** (`app/ai/`): rag.py (grounding + aliases + repeal flags) · vector_store.py (Chroma seed/reseed, de-dup guard, reseed now **raises** if the old collection survives deletion) · ingest_statutes.py (deterministic pdfplumber parser + per-act registry with opt-in flags: `wrapped_headings`, `double_endash`, `article_schedule`, `chain_loose_starts`) · corpus_updates.py (manifest, fingerprint, drift check) · safety.py + soul.py (doctrine) · data_boundary.py (prompt **log-redaction** — keeps matter content out of shared logs; NB it does NOT gate what reaches the LLM, and consent is not yet enforced at the AI boundary — see docs/PRIVACY_DATA_FLOW.md) · agent.py, evals/, activity_tracker, observability.

---

## 4. Legal corpus — the crown jewel

**50 acts as source-verified full text · 8,442 sections · 8,646 embedded chunks · fingerprint `2965aab084ff`.**

- Sources: official India Code bitstreams; ITA-2025 from the Income Tax Department portal; IT Rules 2026 from the Gazette (G.S.R. 198(E)). **No scraping, no commentaries, no AI-generated legal text, no LLM anywhere in ingestion.**
- Every section carries verbatim text, source URL, source SHA-256, page, fetch date.
- Landmark-content acceptance: acts admitted only when landmark sections verify by **content keyword** (key-presence checks banned after the Art.21-Schedule incident).
- Repeal/currency: IPC/CrPC/Evidence → BNS/BNSS/BSA (01-07-2024); Income-tax 1961 → ITA-2025 (01-04-2026) — repeal flags fire in every citation.
- Fingerprint hashes **source sha256 + parsed-content sha per act** (hardened 2026-07-20; previously source-only, which missed parser-level changes).
- Known limitations (disclosed): income_tax_1961 heading-grade (historical use); Constitution Schedules 1-6/8/9/11/12 not ingested; act-level (not per-section) amendment dates; no judgment corpus.
- **Acquisition queue: EMPTY** as of 2026-07-20. Remaining corpus work (per-section amendment dates, judgments) is owner-gated.

Recent slices (all 2026-07-20): ITA-2025 (537 sections, `chain_loose_starts` parser recovery of 9 swallowed sections incl. prosecution provisions) · corpus relocation to D: · completeness slice (Limitation 137→169 — all 137 Schedule articles incl. Arts. 136/137; repeal-stub recovery via `(?!\[)` footnote-filter fix across Limitation/IPC/Evidence; IPC ss.57/60 de-contaminated).

---

## 5. Safety & compliance posture

- **Soul (fail-closed):** refusal doctrine, banned phrases, no-legal-advice boundaries — boot-blocking integrity check.
- **Eval gates in CI (deterministic, 100% must pass):** 15 safety cases (refusal/citation/banned-phrase/intent) + **28 high-stakes retrieval cases** (bail bars, sanction gates, repeal flags, ITA-2025, Limitation condonation/Art.137).
- **Data boundary:** prompt content is log-redacted (`data_boundary.redact_for_log`) so matter data never lands in shared logs. [CORRECTED 2026-07-22: an earlier draft said "tenant data excluded from AI calls absent consent" — verification shows consent is NOT wired into the AI path; enforcing it is an open G6 item. See docs/PRIVACY_DATA_FLOW.md.]
- **DPDP-aligned features:** data_rights router (access/erasure), audit coverage + retention tests, misuse reporting, backup/restore drill tests.
- **Billing safety:** live mode gated on `BILLING_LIVE_APPROVED` + G6/G7 (`assert_billing_mode_allowed`).
- **Human gates (never self-certified, all currently OPEN/UNSIGNED):**
  - **G1** corpus authenticity — packet READY-UNSIGNED (`docs/legal-review/G1_CORPUS_AUTHENTICITY_PACKET.md`, refreshed today).
  - **G6** privacy review · **G7** security review — required before any real client data.
  - **G8** senior-advocate sign-off (drafting templates + AI behaviour) — packet ready-unsigned.

---

## 6. Testing

- **~60 test files** (65 directory entries incl. conftest + e2e); **511 passed / 0 failed** on this date (three full-suite certifications ran today: post-ITA-2025, post-D:-move, post-completeness-slice).
- Coverage spans: parser (17 tests incl. stub-filter + corpus-data pins), corpus updates/drift, retrieval evals, data boundary, audit, backups/restore, billing (incl. disabled mode), consent, child-tenant isolation, documents, drafts, workbench uploads.
- 5 live-NVIDIA test files excluded from the fast lane by design (wall time), included in full runs.

---

## 7. Known risks & pending items

| Item | Status |
|---|---|
| C: drive chronically full | **Chronic** — hit 43 MB free today (silent reseed no-op, now raises). Corpus moved to D:; owner should still clean C:. |
| Prod (EC2) runs pre-slice corpus | Deploy gated on owner starting the new DB cluster (Aurora); AWS billing is owner-only. |
| Human gates G1/G6/G7/G8 | All packets prepared; signatures outstanding. No real client data until G6/G7. |
| ITA-2025 drift monitoring | Source URL is WAF-protected → weekly check reports `error` honestly (by design, never auto-ingests). IT Rules 2026 source is a landing page → `skipped_no_pdf`. |
| income_tax_1961 | Heading-grade (flagged, repeal-flagged); acceptable for historical citation only. |
| ipc_1860 `354E` duplicate | Known upstream mis-print; seeder de-dups (first-wins) every reseed. |
| "Article N ≤ 32" lookup edge | Limitation body section wins over same-numbered Schedule article (deliberate; litigated articles 65/113/136/137 unaffected). |
| Amendment dates | Act-level only; per-section dates = dedicated future slice ("wrong dates are worse than none"). |
| Judgments corpus | Owner decision C-04 (Indian Kanoon live links meanwhile, marked unverified). |
| datetime.utcnow deprecation warnings | 964 warnings in suite (cosmetic, Python 3.12; future cleanup). |

---

## 8. Bottom line

The platform is feature-complete for its current phase: a hardened, provenance-obsessed
statutory corpus (50 acts, zero acquisition backlog), a fail-closed safety doctrine, a
deterministic retrieval layer with eval gates in CI, and a full practice-management suite —
all certified green (511/0) on today's build. What stands between this build and production
with real client data is **human sign-off (G1/G6/G7/G8) and the owner-gated Aurora deploy**,
not engineering work.

*Prepared by the build system 2026-07-20. This report describes; the human gates decide.*
