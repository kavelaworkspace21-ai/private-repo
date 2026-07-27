# Personal Data Flow Map

**Date:** 2026-07-25 · **Scope:** every place personal data enters, is stored, or leaves.
**Method:** schema walk + call-graph tracing + tests that fail if the property regresses.

Two things make this app unusual and shape the whole analysis:

1. **Most personal data here is not the user's — it is their clients'.** An advocate types
   third-party facts (names, allegations, medical details) into chat and uploads case files.
   The data principal is frequently *not* the account holder, which is a live G6 question.
2. **The AI boundary is the only routine external transfer of that data.**

---

## 1. Collection points → where the data goes

| Entry point | Data collected | Stored in | Leaves the system? |
|---|---|---|---|
| `POST /api/auth/register` | full name, email, phone, password | `users` (password → bcrypt hash only) | No |
| `POST /api/auth/login` | email, password | not stored; verified against hash | No |
| `POST /api/auth/consent` | **source IP, user-agent**, policy version | `consent_records` | No |
| `POST /api/auth/2fa/setup` | generated TOTP secret | `users.totp_secret`, **Fernet-encrypted at rest** | Shown once to the user (necessary) |
| `POST /api/clients/` | client name, email, phone, address | `clients` | Only if the advocate sends it to AI |
| `POST /api/cases/`, hearings, diary, fees | matter facts, court, judge, opposing counsel | `cases`, `hearings`, `diary_*`, `fees_*`, `opposing_counsel` | Only via AI |
| `POST /api/documents/upload` | uploaded file + filename | `documents`/`document_versions` + tenant-separated disk | No |
| `POST /api/workbench/uploads` | **client case files**, extracted text | `workbench_uploads` + extracted-text/anchor files on disk | Content goes to the LLM on use |
| `POST /api/ai/chat` | free-text query (**routinely client facts**) | `conversations`, `ai_messages`, `user_activities` (80-char preview) | **Yes → LLM provider** |
| `POST /api/ai/transcribe` | audio clip | not persisted | **Yes → transcription provider** |
| `POST /api/billing/checkout` | GSTIN, seat count | `subscriptions` | No (test mode makes no network call) |
| Every request | client IP (in-memory rate limiting) | not persisted | No |

---

## 2. Where personal data leaves the system

| Destination | What is sent | Gate |
|---|---|---|
| **NVIDIA NIM** (LLM) | the query + retrieved statute text + any matter/document text the advocate includes | Consent enforced at the boundary (`require_ai_user`); refused without it |
| **Transcription provider** (optional, unset) | raw audio | Same consent gate |
| **Indian Kanoon** (paid) | a search phrase or document id — advocate-authored, so may carry matter details | Consent gate + `KANOON_ENABLED` (default **off**) |
| **eCourts** (dormant) | case number / court identifiers | Inert unless `ECOURTS_API_BASE` set |
| **SMTP** (optional) | password-reset token to the user's **own** address | Only to the address on the account |
| **Razorpay** | nothing in test mode — no network call at all; live billing blocked pending G6/G7 | `BILLING_MODE=test` |
| **Sentry** (optional) | error events, **scrubbed** (see §4) | Off unless `SENTRY_DSN` set |

Not an egress: **embeddings and retrieval run locally** (ONNX MiniLM + ChromaDB). No query
text is sent anywhere to be embedded.

---

## 3. Findings and fixes

### 🔴 F1 — "Delete my account" did not delete the data (FIXED)

`DELETE /api/account` removed clients, cases, documents, drafts, notifications, consents,
audit rows, users and the tenant — but **left behind**:

| Table | What survived |
|---|---|
| `conversations`, `ai_messages` | the entire AI chat history, verbatim client facts |
| `user_activities` | 80-char query previews, routinely containing client names |
| `workbench_uploads`, `workflow_sessions`, `workflow_artifacts` | uploaded client case files + extracted text, **and the files left on disk** |
| `data_rights_requests`, `misuse_reports` | the user's own DPDP requests |

`Conversation.user_id` declares `ondelete="CASCADE"`, which looks like coverage — but
**SQLite runs with `PRAGMA foreign_keys=0`**, so the cascade fires on PostgreSQL and is a
silent no-op on SQLite. Dev and production disagreed about what deletion means.

Telling a data principal their data was erased while this remained would have been false.

**Fixed:** erasure now explicitly removes AI history, activity trail, workbench rows and
their on-disk files, and request records — deleting rather than relying on a cascade, so
both backends behave identically. Financial records (`invoices`, `subscriptions`,
`usage_events`) are **anonymised, not deleted**, because Indian tax/GST rules require
invoice retention; the row survives, the person does not.

**Guarded by** `tests/test_erasure_completeness.py`, which walks `Base.metadata` and fails
if *any* tenant/user-scoped table holds rows after erasure. A newly added table fails the
test until someone decides how erasure treats it — the default is no longer "kept forever".

### 🟠 F2 — Sentry would have shipped passwords and client text (FIXED)

`send_default_pii=False` was set, which covers IP, cookies and headers. It does **not**
stop the SDK shipping **local variables from every stack frame** — and the frame that
raises is exactly the one holding `password`, `email`, or the chat message.

**Fixed:** `include_local_variables=False` plus a `before_send` scrubber that redacts
sensitive keys from request data, headers, cookies, breadcrumbs and extras. The scrubber is
depth-capped and never raises — a failure there would discard the error report and hide the
incident.

### 🟠 F3 — Email and phone cached in localStorage (FIXED)

`/api/auth/me` returns email, phone and professional_id. The nav chip cached the **whole
object** in `localStorage` while reading only `full_name`, `role`, `is_2fa_enabled`.
Anything in `localStorage` is readable by any script on the page.

**Fixed:** the cache is now an explicit allow-list of the three fields used. Crucially it
also **purges** the full object from browsers that cached it under the previous build —
writing less from now on would have left existing users' details sitting there. Service
worker bumped v11 → v12, since `utils.js` is served cache-first.

---

## 4. Verified clean (checked, not assumed)

- **Passwords** — bcrypt via passlib. No MD5/SHA1, no SHA-256-alone, nowhere. Never logged,
  never returned, never stored in plaintext; the only consumer is the hashing function.
- **JWT payload** — `sub` (user id), `role`, `type`, `exp`. No email, no name.
- **Logging** — 64 call sites reviewed. None interpolates PII. The three `.name` matches are
  `Path.name` (filenames). No `console.log` emits tokens or personal data.
- **API responses** — all **152 routes declare a `response_model`**, so field filtering is
  structural rather than per-endpoint discipline. No schema exposes `hashed_password` or
  `totp_secret`; `password` appears only on *request* models.
- **Cross-tenant** — isolation covered by `test_idor_sweep` and `test_tenant_rbac_deep`.
- **`totp_secret`** — Fernet-encrypted at rest via `EncryptedString`.

---

## 5. Open — needs a human decision, not code

1. **Tokens in `localStorage`.** `access_token`/`refresh_token` live there, so an XSS can
   steal a session. The robust fix is httpOnly + Secure + SameSite cookies, which requires
   adding CSRF protection and reworking every `fetch` call — a real architectural change
   with its own regression risk. **Deliberately not done inside a data-flow audit.** It
   belongs with the G7 penetration-test remediation. Note the app currently sets **no
   cookies at all**, so there is no cookie-flag defect to fix — the exposure is the storage
   choice.
2. **Client consent.** The advocate consents; the client whose data is in the prompt is not
   a party to it. Whether professional authority covers this is a G6 counsel question.
3. **Invoice retention period.** Anonymisation is implemented; the statutory retention
   duration needs a chartered accountant to confirm.
4. **Chat previews in `user_activities`.** Now erased with the account, but they remain a
   second copy of client facts outside the matter. Consider dropping the preview to a
   non-identifying label.

---

*Every claim above is backed by a test or a cited file. Where a control is missing it is
listed in §5 rather than described as handled.*
