# LegalServer.AI — Legal Baseline (LSAI-LEGAL-00)

_Date: 2026-06-23 · Source of truth: the repo (not reports). Not a legal opinion._

## Repo state (verified this session)
- **Tests:** 137 passing (`python -m pytest -q`).
- **API routers (18):** auth, clients, cases, documents, hearings, fees, diary, diary_summary,
  ai_chat, ai_drafting, drafts, research, library, ecourts, notifications, account, audit, firm
  (+ admin endpoints + `/api/account/profile`).
- **Page routes:** `/`, `/cases`, `/diary`, `/library`, `/assistant`, `/drafting`, `/drafts`,
  `/firm` (incl. audit log), `/account`, `/notifications`, `/login`, `/register`, `/setup-2fa`,
  `/reset-password`, `/consent`.
- **Models (22):** incl. Tenant, User, Client, Case + children, GeneratedDraft(+Version),
  DocumentVersion, ConsentRecord, Notification, AuditLog, BackupRun.
- **Deployment:** EC2 + Aurora PostgreSQL (Alembic-migrated), nginx + TLS, free Gemini AI.

## Compliance-relevant guardrails ALREADY present
- **AI safety** (`app/ai/safety.py`): citation hard-gate, no-source refusal, confidence labels,
  banned-phrase block, draft disclaimer, AI-generated notice; drafts start `DRAFT_FOR_ADVOCATE_REVIEW`.
- **Consent:** `ConsentRecord` captured at registration; `GET /api/auth/needs-consent` gate; `/consent` page.
- **Data rights:** `GET /api/account/export`, `DELETE /api/account` (erasure), `GET /api/account/privacy`,
  `PATCH /api/account/profile`; Account UI built.
- **Prohibited features:** Case-Prediction card removed; `tests/test_no_prohibited_features.py` guard.
- **Tenant isolation:** `tenant_id` on every business table; cross-tenant reads → 404; RBAC (clerk read-only).
- **eCourts:** inert unless `ECOURTS_API_BASE` set; graceful "not configured" UX; no scraping/CAPTCHA paths.
- **Security:** field encryption at rest (`EncryptedString` on totp_secret), automated backups (`BackupRun`),
  HTTP security headers, audit log + admin viewer.

## Gaps to close in this program (status as of 2026-06-23)
- Legal policy pack (Terms/Privacy/AUP/Grievance/AI-disclosure/Retention/Subprocessor/Law-enforcement) + routes — **TO BUILD (LEGAL-02)**.
- Consent precision (button-gate, versioned receipts w/ IP+UA+notice_version, re-consent) — **PARTIAL → LEGAL-03**.
- Data map / store disclosure matrix — **TO BUILD (LEGAL-04)**.
- Data-rights request tracker (`DataRightsRequest`) — **TO BUILD (LEGAL-05)**.
- AI no-training boundary doc + redaction guard — **PARTIAL → LEGAL-06**.
- Advocate verification fields/gate — **TO BUILD (LEGAL-07)**.
- Deep tenant/RBAC regression suite — **PARTIAL → LEGAL-13**.
- Incident/breach docs, misuse reporting, law-enforcement register — **TO BUILD (LEGAL-15/16/17)**.
- Billing/GST/refund docs (disabled-safe) — **TO BUILD (LEGAL-18)**.
- App-store packet — **TO BUILD (LEGAL-19)**.
- Legal AI eval suite — **TO BUILD (LEGAL-20)**.
- Human sign-off packet + pre-publish lock — **TO BUILD (LEGAL-21/22)**.

## Human gates — `MISSING / TO BE POPULATED` (never self-certified)
Senior advocate (corpus + AI behaviour), DPDP/privacy reviewer, security reviewer, founder, app-store
owner. **No real client data and no public launch until these are signed off.**
