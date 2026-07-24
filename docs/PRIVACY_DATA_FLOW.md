# Privacy Data-Flow Map

Evidence for the **G6** DPDP/privacy review. Grounded in the models, providers, and retention code.
`[counsel confirms]` marks items for legal review. No real client data until G6+G7 sign.

## Personal-data inventory

| Category | Fields | Where stored | Protection |
|---|---|---|---|
| **Advocate (user)** | name, email, phone; `totp_secret`; password | primary DB (`app/models/user.py`) | `totp_secret` **Fernet-encrypted** (`app/db/crypto.py`); password **bcrypt**; rest plaintext columns → rely on DB storage encryption (🔒 Aurora RDS) |
| **Client** | name, email, phone, address | primary DB (`app/models/client.py`), tenant-scoped | tenant isolation; storage encryption 🔒 |
| **Matter content** | cases, documents, drafts, diary, fees, hearings | primary DB + uploaded files | tenant-scoped; files on local disk today → 🔒 encrypted object storage |
| **AI conversations** | user prompts + assistant answers | DB (`Conversation`/`AiMessage`) | tenant-scoped; retention `[counsel confirms]` |
| **Billing** | firm GSTIN, subscription, invoices, Razorpay ids | DB (`app/models/billing.py`) | `BILLING_MODE=test`; no live payments pre-G6/G7 |

The **corpus/vector store holds NO client PII** — only public source-verified statutory text.

## Data flows to subprocessors (outside the trust boundary)

| Subprocessor | What is sent | When | Notes |
|---|---|---|---|
| **NVIDIA NIM** (LLM, `AI_BASE_URL`) | the advocate's typed **query** (may contain matter facts) + retrieved **corpus** text (public statute) + activity context | every AI answer | `data_boundary.redact_for_log()` keeps prompt content OUT OF SHARED LOGS (not out of the LLM); a no-training statement is surfaced. **⚠ Consent is NOT yet enforced at the AI boundary** (see Consent below) — a G6 gap. Optional tenant-verification gate (`require_ai_access`, off in beta). ⛔ confirm exactly what leaves + provider region/retention/training `[verify]` |
| **Transcription** (`TRANSCRIBE_BASE_URL`, Whisper) | audio clip | only when voice input is used | no-op if unconfigured |
| **Embeddings** | text to embed | corpus indexing / query | **defaults to LOCAL ONNX (nothing leaves)** unless `OPENAI_EMBEDDINGS_KEY` set |
| **Razorpay** | firm + payment metadata | billing (test mode now) | live gated on G6/G7 + owner |
| **SMTP email** (`SMTP_*`) | recipient email + notification text | reminders / password reset | self-hosted SMTP; no-op if unset |
| **Indian Kanoon** (`INDIAN_KANOON_API_KEY`) | search query text | case-law search | read-only; results are unverified links, NOT model grounding |
| **eCourts** (`ECOURTS_*`) | case lookup params | when enabled | read-only, feature-flagged; never scraping |
| **AWS** (Aurora/EC2/S3) | all app data | prod hosting | 🔒 region (recommend ap-south-1), IAM, KMS |

## Retention (what exists)

- **Workbench uploads** — auto-delete after 7 days (`workbench/uploads.purge_expired`, scheduled).
- **Read notifications** — conservative purge (`privacy.purge_old_read_notifications`).
- **Security logs** — ≥180-day floor (CERT-In) `[verify rotation wired]`.
- **Per-model retention schedule** — designed (Phase 2), not fully implemented for all models. ⛔

## Data-principal rights

- Access + erasure: `app/routers/data_rights.py` (`DataRightsRequest`).
- ⛔ **Correction** + **grievance** (SLA) + **nominee** — Phase 2 additions.
- ⛔ **Deletion/export propagation** must be verified end-to-end across: primary DB, uploaded
  files/object storage, Chroma (no PII, but confirm), caches, backups, logs, AI history, and each
  subprocessor. This is the single biggest open privacy verification.

## Consent  ⚠ GAP

A `ConsentRecord` model exists (`app/models/consent.py`), **but verification shows it is NOT wired
into the AI path** — no purpose-consent check runs before a query is sent to the LLM (grep of
`app/ai/` + `ai_chat.py` finds no consent gate). What actually limits exposure today is: prompt
**log-redaction** (`data_boundary`), embeddings defaulting to **local ONNX**, the optional
verification gate, and the no-training statement. **Enforcing itemized, purpose-based consent
(with one-click withdrawal that immediately blocks AI processing) is an open G6 item (Phase 2)** —
do not represent consent as an active control until it is wired and tested. Notice wording is counsel
territory.

## Cross-border

DPDP uses a negative-list transfer model (transfers allowed except to notified restricted countries).
Confirm no configured subprocessor region is restricted at launch `[counsel confirms / re-verify]`.

## Open items for G6 (owner + counsel)

Processor register + DPAs; verified deletion/export propagation; retention schedule per model; breach
mechanics rehearsed (`INCIDENT_RUNBOOK.md`); vendor retention/training-policy confirmations; consent
notice wording. See `docs/GAP_MATRIX.md` + `docs/OWNER_QUEUE.md`.
