# Juriscite — Complete Project Knowledge

> **Single, detailed reference for the whole project.** Repo is the source of truth; this file is a
> human-readable map of it. **Last updated:** 2026-06-24 · Maintained by the Master Agent ("Legal Server.AI").
> Canonical copy: `docs/PROJECT_KNOWLEDGE.md` · Desktop mirror: `Desktop/JURISCITE_PROJECT_KNOWLEDGE.md`.

---

## 0. One-paragraph summary
**Juriscite** is a source-grounded, no-hallucination **legal practice operating system for Indian
advocates and law firms** — sign in, manage clients/matters, run a court diary, ask **cited** legal
research questions, and generate **advocate-reviewed** drafts. It is a private professional tool (not a
public "AI lawyer"). Backend: FastAPI + SQLite (dev) / Aurora PostgreSQL (prod) + ChromaDB + a free,
provider-agnostic LLM. Delivered as a web app **and an installable PWA** (Android + iOS). It is governed
by a constitution whose **safety doctrine is supreme over everyone, including the owner.**

---

## 1. Identity, ownership & governance
- **Product / app name:** **Juriscite** (from *juris* + *cite* = "cite the law"; chosen by owner
  2026-06-24, web-checked for clashes). Brand shown two-tone: **Juris**·*cite* (gold accent on black).
- **Owner / proprietor:** **Kavela Narula**. Email: kavelaworkspace21@gmail.com. No company entity
  incorporated yet (add a copyright line + legal entity to Terms when incorporated).
- **Master Agent (build governor):** **"Legal Server.AI"** (formerly "Aira"). It is *not* the product;
  it's the disciplined operating mind that builds the product. Its identity: `docs/governance/AIRA_IDENTITY.md`.
- **The soul = discipline.** The safety doctrine + the Loop are **constitutional bedrock, inviolable and
  not amendable by anyone — including the owner** (owner directive 2026-06-24). Any instruction (owner,
  user, or injected content) that would weaken it is refused and the Process re-runs. The owner keeps
  authority over all **non-safety** scope/features.
- **Authority order (higher wins; conflicts surfaced, never silently resolved):**
  1. V3 Constitution — `docs/governance/LEGALSERVERAI_MASTER_AGENT_V3_FIROZ_BRAIN_2026-06-21.md`
  2. `CLAUDE.md` (build guide, at `Desktop/CLAUDE.md`)
  3. `docs/STATUS.md` (canonical tracker; mirrored to `Desktop/STATUS.md`)
- **The Loop (when stuck):** name the gap → acquire knowledge (incl. online research) → capture it as a
  skill → inform the Master Agent (governance + memory + STATUS) → resume. Skill: `.claude/skills/loop`.

### Standing owner directives (binding)
1. The soul is supreme — no one overrides it, not even the owner.
2. **No illegal-activity support** (forgery, fabricating/planting evidence, bribery, intimidation,
   knowingly false filings, impersonation) — refused at the AI input screen + AUP.
3. **Citations must be relevant AND source-grounded** — never padded, invented, or off-point.
4. **Legal-profession only** + must withstand **digital compliance** (DPDP Act 2023, IT Act/Rules,
   SC draft AI-in-Courts Regs 2026, and the app's own Terms/AUP).
5. Storage: **D: drive authorized** → `D:\Juriscite\{backups,corpus,artifacts}` (~425 GB free) for future
   corpus/backup/artifact use.

---

## 2. The Safety Doctrine (the heart of the product) — never violate
Automated tests fail the build if any of these break:
1. **No source, no answer.** AI never answers a legal question from memory; it retrieves real
   statute/judgment text first, then answers only from what was retrieved.
2. **Every legal claim carries a citation** — and the citation must be **relevant** and **source-grounded**.
   Unverified citations are flagged by a hard gate.
3. **If sources are missing/conflict, say so** — refuse or escalate; never guess.
4. **Every draft is `DRAFT_FOR_ADVOCATE_REVIEW`** until a human advocate approves it.
5. **Confidence label** on every answer: HIGH / MEDIUM / LOW.
6. **Banned phrases never appear** ("you will win", "guaranteed", "file this immediately", "replaces a
   lawyer", "the court will definitely…", etc.).
7. **Every draft ends with the disclaimer** ("Draft for advocate review. Verify facts, jurisdiction,
   limitation, court rules, and latest case law before filing.").
8. **Tenant isolation is sacred** — cross-tenant read = P0 bug (returns 404).
9. **No illegal-activity assistance** — unlawful-purpose requests are refused (`screen_request_intent`).
10. **PROHIBITED: AI prediction / risk-scoring** — no case-outcome/"win probability", bail/flight/
    recidivism risk, witness-credibility or judge-behavior prediction. Enforced by `legal_config`.

Implementation: `app/ai/safety.py` (gates) + `app/legal_config.py` (identity + prohibited flags + launch
lock) + tests `tests/test_safety.py`, `tests/test_no_prohibited_features.py`, `tests/test_legal_eval_suite.py`.

---

## 3. Tech stack
- **Backend:** Python, FastAPI, SQLAlchemy 2.0, Pydantic.
- **DB:** SQLite (local dev) / **Aurora PostgreSQL** (prod, in-VPC on EC2). Alembic migrations.
- **Vector search / RAG:** ChromaDB with **free local ONNX embeddings** (no key); optional OpenAI
  embeddings only if `OPENAI_EMBEDDINGS_KEY` set.
- **LLM:** provider-agnostic via OpenAI-compatible API (`app/ai/llm_config.py`). Zero-cost default:
  **Google Gemini `gemini-2.5-flash-lite`** (free tier). Streaming via `create(stream=True)`.
- **Frontend:** server-rendered HTML + vanilla JS (black/gold theme), single shared `style.css` +
  `utils.js`. **Installable PWA** (manifest + service worker + icons).
- **Background jobs:** APScheduler (daily reminders 07:00, daily backup 02:00).
- **Exports:** DOCX + PDF (drafts), `.ics` (court diary calendar).
- **Auth:** JWT (access + refresh), bcrypt password hashing, **TOTP 2FA**, password reset, RBAC, multi-tenant.
- **Native mobile (scaffolded, owner-gated):** Capacitor wrapper in `mobile/`.

---

## 4. Repository structure (key paths)
```
LEGAL SERVER CLAUDE/
├─ app/
│  ├─ main.py                 FastAPI app: middleware, routers, page routes, PWA routes, admin, legal
│  ├─ legal_config.py         identity flags, PROHIBITED features, LAUNCH_GATES + pre-publish lock
│  ├─ auth/                   security.py (JWT/hash/TOTP), dependencies.py (RBAC, gates), config.py
│  ├─ db/                     config.py (engine), session.py, base.py, crypto.py (EncryptedString)
│  ├─ models/                 24 SQLAlchemy models (see §6)
│  ├─ routers/                20 API routers (see §7)
│  ├─ services/               business logic: tenancy, privacy, backup, email, notifications,
│  │                          mapping, storage, ratelimit, library, calendar_export
│  ├─ ai/                     agent.py (RAG agent), safety.py (doctrine), llm_config.py,
│  │                          vector_store.py, case_law.py, data_boundary.py, activity_tracker.py,
│  │                          evals/legal_eval_set.py (LEGAL-20)
│  ├─ integrations/           ecourts.py (read-only, flag-gated, no scraping)
│  ├─ schemas/                Pydantic request/response models
│  ├─ templates/              17 HTML pages (dashboard, cases, diary, library, assistant, drafting,
│  │                          drafts, firm, account, notifications, legal, login, register, etc.)
│  └─ static/                 style.css, utils.js, page JS, PWA (manifest.webmanifest, service-worker.js,
│                             offline.html, icons), favicon.svg
├─ migrations/versions/       11 Alembic migrations (head = d7e3b1a9c4f2)
├─ mobile/                    Capacitor scaffold (capacitor.config.json, package.json, www/)
├─ tests/                     pytest suite — 237 tests passing (unit/api/security/AI/e2e)
├─ docs/
│  ├─ STATUS.md               canonical tracker (mirrored to Desktop)
│  ├─ PROJECT_KNOWLEDGE.md    THIS FILE
│  ├─ governance/             V3 constitution + AIRA_IDENTITY.md + skills/ (22 LSAI-SKILL + INDEX)
│  ├─ legal/                  ~26 policy/compliance docs (see §9)
│  └─ deployment/             MOBILE_BUILD_GUIDE.md, etc.
├─ legal-data/                corpus (raw/processed/chunks/metadata)
├─ requirements.txt           Python deps
└─ .env.example               env template (no secrets)
```
Plus on Desktop: `CLAUDE.md` (build guide), `STATUS.md` + `JURISCITE_PROJECT_KNOWLEDGE.md` (mirrors).
Memory: `C:\Users\prith\.claude\projects\…\memory\` (MEMORY.md index + fact files).

---

## 5. Core modules / features (what the app does)
1. **Auth + RBAC + tenancy** — register (creates a firm/tenant), login (JWT), refresh, password reset,
   TOTP 2FA (mandatory for advocate/judge/firm_admin/business), roles, AuditLog on mutations.
2. **Firm workspace** — invite members (seat limit 14), set roles, deactivate; never leave a tenant
   without an active admin; member consent-on-first-login.
3. **Clients & Matters** — client CRUD, matter (case) CRUD with court/case metadata, opposite party,
   assigned advocate, notes.
4. **Documents** — upload + versioning (every change = a `DocumentVersion`); tenant-scoped storage.
5. **Court Diary** — hearings, diary entries, tasks, filing deadlines; daily/weekly views; next-date;
   reminders (worker jobs); `.ics` calendar export; optional eCourts pull (read-only, flag-gated).
6. **Fees** — fee collected + fee due ledgers (agreed/received/balance), auditable.
7. **Cited Research Assistant** — RAG over the legal corpus; streaming chat (SSE); citation hard-gate;
   confidence labels; "no source, no answer" refusal; query history; **unlawful-purpose input screen**.
8. **Legal Library + Case Law** — browse corpus sections; section summaries; old↔new statute mapping
   (BNS/BNSS/BSA ↔ IPC/CrPC/Evidence) flagged as advocate-unverified; live Indian Kanoon (cached).
9. **Drafting Engine** — 10 templates (Legal Notice s.80 CPC, Cheque Dishonour s.138 NI, Anticipatory
   Bail, Regular Bail, Affidavit, RTI, Consumer Complaint, Vakalatnama, Writ Petition, Divorce Petition);
   streaming generation; starts `DRAFT_FOR_ADVOCATE_REVIEW` + disclaimer; **DOCX/PDF export**; advocate
   **approve** workflow; **draft versioning** (save→v1, edit→new version re-opens review, revert).
10. **Notifications** — reminder bell + center (list, unread count, mark read, run reminders).
11. **Account & Data Rights (DPDP)** — profile edit; 2FA/password; privacy statement; **data export**
    (right to access); **account deletion** (right to erasure); **data-rights request tracker**; **misuse
    /abuse reporting**.
12. **Audit** — firm-admin audit-log viewer (who/what/when/tenant).
13. **Admin** — corpus reseed/ingest; DB backups (manual + daily); **founder-only verification** of
    advocates/firms (X-Admin-Token).
14. **Legal/Policy hub** — `/legal` serves the full policy pack as in-app pages.

---

## 6. Database models (24 tables) — all carry `tenant_id` where business data
`Tenant` (firm; + verification: status/jurisdiction/bar_enrolment/verified_at), `User` (role enum:
advocate/judge/firm_admin/business/associate/clerk; 2FA fields, professional_id, is_active),
`AuditLog`, `Client`, `Case`, `Document`, `DocumentVersion`, `Hearing`, `FeeCollected`, `FeeDue`,
`DiaryEntry`, `DiaryTask`, `FilingDeadline`, `OpposingCounsel`, `Conversation`, `AiMessage`,
`UserActivity`, `GeneratedDraft`, `GeneratedDraftVersion`, `Notification`, `ConsentRecord`
(+ user_agent/acceptance_source receipt fields), `BackupRun`, `DataRightsRequest`, `MisuseReport`.

Rules: every business table has `tenant_id`; AI answers carry source_ids; every doc gen creates a
version; important mutations write `AuditLog`; consent stored in `ConsentRecord`; drafts start in review.
Migrations only (Alembic); never hand-edit the DB. Child rows auto-inherit `tenant_id` from their Case.

---

## 7. API routers (20) and where they mount
`/api/auth` (auth, consent, verification submit), `/api/clients`, `/api/cases`, `/api/documents`,
`/api/hearings`, `/api/fees`, `/api/diary` (entries/tasks/deadlines/opposing-counsel + summary),
`/api/ai` (chat), `/api/drafting` (generate + export), `/api/drafts` (save/edit/approve/versions/revert),
`/api/research` (mapping/cases/status), `/api/library`, `/api` (ecourts + calendar), `/api/notifications`,
`/api/account` (export/delete/privacy/profile), `/api/data-rights`, `/api/misuse`, `/api/audit`, `/api/firm`.
Admin (in `main.py`): `/api/admin/{reseed-corpus,ingest-statutes,backup,backups,pending-verifications,
verify/{tenant_id}}`. Legal: `/api/legal/{identity,index,doc/{slug}}`. System: `/health`.

### Page routes
`/`, `/cases`, `/diary`, `/library`, `/assistant`, `/drafting`, `/drafts`, `/firm`, `/account`,
`/notifications`, `/legal`, `/legal/{slug}`, `/login`, `/register`, `/setup-2fa`, `/reset-password`,
`/consent`. PWA: `/manifest.webmanifest`, `/service-worker.js`, `/offline`.

---

## 8. AI layer (RAG, zero-cost, safe)
- **Config:** `app/ai/llm_config.py::ai_config()` → {api_key, base_url, model} from `AI_API_KEY/AI_BASE_URL/
  AI_MODEL`, else OpenAI fallback. One controlled outbound path used by agent, drafting, library, case_law.
- **Retrieval:** `vector_store.py` (ChromaDB; free local embeddings).
- **Agent:** `agent.py` retrieves → answers only from sources → confidence label → citation gate.
- **Safety:** `safety.py` — `is_answerable`, `assess_confidence`, `find_banned_phrases`/`sanitize_answer`,
  `extract_citations`/`enforce_citations`, `ensure_draft_disclaimer`, `screen_request_intent` (unlawful).
- **Data boundary:** `data_boundary.py::redact_for_log` keeps prompts out of shared logs; **no training on
  client data**.
- **Evals:** `app/ai/evals/legal_eval_set.py` — deterministic safety eval set (15 cases @ 100%): no-source
  refusal, citation gate, banned-phrase, unlawful-intent. Live-LLM hallucination grading needs G8 (human).

---

## 9. Legal-compliance pack (LEGAL-00 → 22) — COMPLETE
Docs live in `docs/legal/` and are served at `/legal`. Each item has code/tests where applicable.
- **00** Legal baseline · **01** Product identity · **02** Policy pack + `/legal` routes (Terms, Privacy,
  Acceptable Use, Grievance, AI-Disclosure, Retention, Subprocessors, Law-Enforcement).
- **03** Consent precision (provable receipts: IP + user-agent + acceptance_source + versions; versioned
  consent screen). **04** Data Map & Store-Disclosure Matrix. **05** Data-Rights request tracker.
  **06** AI data-boundary (no-training + log redaction). **07** Advocate/firm verification + AI access gate.
- **08** AI safety hardening (unlawful-purpose screen). **09** Prohibited-features guard. **10** Advertising/
  solicitation (BCI Rule 36) policy + UI guard. **11** eCourts integration policy + AST no-scraping guard.
  **12** Access-control & roles doc. **13** Deep tenant/RBAC isolation suite.
- **15** Incident/breach response. **16** Misuse reporting (model + API + UI). **17** Law-enforcement
  request register. **18** Billing/GST/refund (billing DISABLED + route guard). **19** App-store privacy packet.
- **20** Deterministic AI eval suite. **21** Human sign-off packet. **22** Fail-closed pre-publish lock.
Docs also: `AI_SAFETY_POLICY.md`, `ACCESS_CONTROL_AND_ROLES.md`, `ADVERTISING_SOLICITATION_POLICY.md`,
`ECOURTS_INTEGRATION_POLICY.md`, `HUMAN_SIGNOFF_PACKET.md`, `PRE_PUBLISH_LOCK.md`, `PROHIBITED_FEATURES.md`,
`LEGAL_BASELINE_2026-06-23.md`.

---

## 10. PWA & native mobile
- **PWA (built, install-ready both platforms):** `app/static/manifest.webmanifest`, root-scope
  `app/static/service-worker.js` (offline shell; **never caches `/api`/tenant data**), `offline.html`,
  gold-"J" icons (192/512/maskable/180 apple-touch). Served at `/manifest.webmanifest` + `/service-worker.js`;
  injected on every page by `utils.js::injectPWA` (+ Android "Install Juriscite" button, iOS meta).
  Install: Android Chrome → "Install app"; iOS Safari → "Add to Home Screen". Tests: `tests/test_pwa.py`.
  **Requires trusted HTTPS in production** (SW won't register on the self-signed cert → needs domain+certbot).
- **Native store apps (scaffolded, owner-gated):** `mobile/` Capacitor wrapper + `docs/deployment/
  MOBILE_BUILD_GUIDE.md`. **Owner must provide:** a Mac (iOS can't build on Windows), Apple Developer
  ($99/yr) + Google Play ($25) accounts, and signing certs. (Account creation + credential handling are
  outside what the agent may do.)

---

## 11. Deployment (current)
- **EC2 + Aurora:** app runs as systemd service `legalserver` (uvicorn :8000) on an EC2 box (Python venv,
  `.env`), Aurora PostgreSQL migrated via `alembic upgrade head`. nginx + TLS (self-signed) reverse proxy
  (:443→:8000, SSE-friendly `proxy_buffering off`, :80→:443). 2 GB swap for embeddings on the small box.
- **Why DB work runs on the bastion:** laptop→Aurora TLS stalls (path-MTU blackhole); bastion→Aurora is
  in-VPC and instant. Runbook: `docs/governance/skills/LSAI-SKILL-10`.
- **DEPLOYED 2026-06-25** to EC2 + Aurora — code synced, Aurora migrated to **head `d7e3b1a9c4f2`**,
  `legalserver` restarted, on-box `/health` = `soul: intact`, rebrand + PWA live. **External 443 is still
  blocked by the EC2 security group** (SSH-only) → owner opens SG 443/80 + adds domain/cert for public use.

---

## 12. Testing
- **237 tests passing, 0 failures** (`venv\Scripts\python -m pytest tests/ -q`, ~2-4 min).
- 42 test files + `tests/e2e/test_journey.py` (the end-to-end advocate journey). Coverage spans: safety
  doctrine, RBAC, **deep tenant isolation**, privacy/DPDP, consent precision, data-rights, misuse,
  verification, AI data-boundary, citation gate, eval suite, prohibited-features + solicitation + eCourts
  guards, billing-disabled, pre-publish lock, PWA routes, migrations drift guard, backups, encryption,
  security headers, rate limit, reminders, drafts/versions, documents, library, research/mapping.
- Test DB is a throwaway SQLite per test (`tests/conftest.py`); `create_all` builds schema; rate limiting
  disabled in tests.

---

## 13. Human gates (NEVER self-certified) — all OPEN
- **G1** corpus authenticity (senior advocate) · **G6** privacy review (DPDP reviewer) · **G7** security
  review · **G8** senior-advocate AI/template sign-off · closed-beta validated · willingness-to-pay.
- Encoded in `legal_config.LAUNCH_GATES` (all False) → `public_launch_blocked()` is **True** (fail-closed).
  **No real client data and no public launch until G6 + G7 signed; no public AI claims until G1 + G8.**
- Sign-off packet: `docs/legal/HUMAN_SIGNOFF_PACKET.md`; lock: `docs/legal/PRE_PUBLISH_LOCK.md`.

---

## 14. How to run / common commands
From the project root (`C:\Users\prith\OneDrive\Desktop\LEGAL SERVER CLAUDE`), venv at `venv\Scripts\`:
```powershell
# Run the app (dev)
venv\Scripts\python.exe -m uvicorn app.main:app --reload      # http://127.0.0.1:8000
# Tests
venv\Scripts\python.exe -m pytest tests/ -q
venv\Scripts\python.exe -m pytest tests/e2e -q                 # the e2e journey
# Migrations
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe -m alembic revision --autogenerate -m "msg"
```
Demo login (local): `demo@legalserver.ai` / `DemoPass@123` (2FA disabled on that account).
Founder admin actions need header `X-Admin-Token: <ADMIN_TOKEN env>`.

---

## 15. Configuration (.env — see `.env.example`)
`DATABASE_URL` (SQLite dev / Aurora prod), `JWT_SECRET`, `ACCESS/REFRESH_TOKEN_EXPIRE_*`, `APP_NAME`,
AI: `AI_API_KEY`/`AI_BASE_URL`/`AI_MODEL` (free Gemini/Groq/Cerebras; falls back to `OPENAI_API_KEY`),
`OPENAI_EMBEDDINGS_KEY` (optional; default free local), `FIELD_ENCRYPTION_KEY` (Fernet; else derived from
JWT_SECRET in dev), `INDIAN_KANOON_API_KEY`, `ECOURTS_API_KEY`/`ECOURTS_API_BASE` (blank = inert),
`RATELIMIT_ENABLED`, `BACKUP_DIR`/`BACKUP_KEEP`, `ADMIN_TOKEN` (founder actions), `AI_REQUIRES_VERIFICATION`
(default off). **Never commit a real `.env`; never put secrets in chat.**

---

## 16. Governance skill pack (22) — `docs/governance/skills/` (see INDEX.md)
01 Legal-AI Safety/No-Hallucination · 02 Indian Legal Corpus Provenance · 03 Citation Hard-Gate/Good-Law ·
04 DPDP Privacy/Consent/Data-Rights · 05 Advocate Ethics (BCI Rule 36) · 06 Human Advocate Drafting ·
07 Tenant Isolation/RBAC/BOLA · 08 Audit Ledger/Evidence · 09 Secure SaaS Infra/Secrets · 10 PostgreSQL/
PGVector/Alembic · 11 Backup/Restore/DR · 12 Document Security/Storage/Versioning · 13 eCourts/External
Integration Safety · 14 Legal-AI Eval/Red-Team · 15 LLM Security/Prompt-Injection · 16 Billing/GST/SaaS
Entitlement · 17 Mobile PWA/MASVS Readiness · 18 Advocate-Centric UX · 19 Observability/SRE/Incident ·
20 Human-Gate Governance/Release · 21 AI Transparency/Court-Filing Disclosure · 22 Commercial Pilot/Beta Ops.

---

## 17. What's DONE vs PENDING (truthful)
**DONE (buildable scope, all local-verified):** all 10 core modules; full legal pack LEGAL-00→22; safety
doctrine + eval suite; tenant isolation + RBAC; DPDP consent/export/erasure/data-rights/misuse; advocate
verification + AI access gate; zero-cost AI (research/drafting/case-law/library, DOCX/PDF/.ics export);
backups, field encryption, security headers, rate limiting, audit; Juriscite rebrand; installable PWA;
Capacitor scaffold + guide; 237 tests green; deployed live to EC2+Aurora; STATUS + memory current.
**Production discipline (2026-06-25):** CI workflow (`.github/workflows/ci.yml` — pytest + migration
single-head + drift guard, advisory ruff + pip-audit); observability (`app/observability.py` — X-Request-ID
on every response + optional env-guarded Sentry); Docker packaging (`Dockerfile` + `docker-compose.yml`
api+postgres+redis for local/staging); backup **restore-drill** (`backup.verify_backup` + test).

**PENDING — owner/human-gated (NOT code I can finish):**
1. **Deploy today's build to EC2 + `alembic upgrade head` on Aurora** (6 newer migrations).
2. **Domain + trusted TLS cert** (certbot) → enables public PWA install + removes self-signed cert.
3. **Open EC2 security-group ports 443/80.**
4. **Human gates G1/G6/G7/G8** (senior advocate + DPDP + security reviewers) — required before real client
   data / public launch; pre-publish lock stays engaged until signed.
5. **Native store apps** — needs Mac + Apple/Google dev accounts + signing (owner).
6. **More verbatim corpus PDFs** (founder-supplied) to expand source-grounded coverage.
7. Optional: Docker packaging; per-tenant AI toggle; semantic relevance gate enhancement.

**Deferred per CLAUDE.md §1 (do not build):** paid self-serve billing; public AI-lawyer; lawyer
marketplace/ranking; lead generation; AI prediction/risk-scoring (**prohibited**).

---

## 18. Where knowledge is stored (so you can always find it)
- **This file:** `docs/PROJECT_KNOWLEDGE.md` (canonical) + `Desktop/JURISCITE_PROJECT_KNOWLEDGE.md` (mirror).
- **Status / resume point:** `docs/STATUS.md` + `Desktop/STATUS.md`.
- **Constitution & soul:** `docs/governance/` (V3 constitution, `AIRA_IDENTITY.md`, 22 skills).
- **Build guide:** `Desktop/CLAUDE.md`.
- **Policies:** `docs/legal/*.md` (also served at `/legal`).
- **Agent memory (cross-session):** `C:\Users\prith\.claude\projects\C--Users-prith-OneDrive-Desktop-LEGAL-SERVER-CLAUDE\memory\`
  (`MEMORY.md` index + fact files: project-owner, feedback-owner-directives, reference-master-agent,
  project-current-status, feedback-loop-protocol, etc.).
- **Future bulk storage:** `D:\Juriscite\{backups,corpus,artifacts}`.
```
```
_End of project knowledge. Update this file whenever the architecture or scope changes._
