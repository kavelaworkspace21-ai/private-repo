# Threat Model

Evidence for the **G7** security review. Grounded in the actual codebase; each control cites where
it lives. `✅` implemented · `🟡` partial · `⛔` missing (agent-ownable) · `🔒` owner-infra.
Status: app `0.2.0` · 556 tests passing · no real client data (pre-G6/G7).

## Assets

- **Client/matter PII** — `Client` (name, email, phone, address; `app/models/client.py`), cases,
  documents, drafts, diary, fees, AI conversations. Tenant-scoped via `tenant_id`.
- **Advocate accounts** — `User` (name/email/phone; `totp_secret` **Fernet-encrypted at rest**,
  `app/db/crypto.py::EncryptedString`), password hashes (bcrypt).
- **The corpus** — source-verified statutory text (integrity-critical; fingerprint `2965aab084ff`).
- **Secrets** — `JWT_SECRET`, `FIELD_ENCRYPTION_KEY`, provider keys, `RAZORPAY_*`.

## Trust boundaries

Browser/PWA → API (FastAPI) → DB (SQLite dev / **Aurora prod**) · Vector store (Chroma, local
sqlite) · Subprocessors (NVIDIA NIM, Whisper transcription, Razorpay, SMTP, Indian Kanoon, eCourts).
The advocate is trusted-but-authenticated; other tenants are adversaries; all subprocessors are
outside the trust boundary.

## Surfaces, threats, controls

| Surface | Threats | Controls (where) | Gaps |
|---|---|---|---|
| **AuthN** | credential stuffing, brute force, token theft | bcrypt; TOTP 2FA (`totp_secret` encrypted); JWT (`app/auth/`); login/forgot/register rate limits (`app/services/ratelimit.py` — 20/5min, 5/15min, 10/hr per IP) | 🟡 in-memory limiter (per-process; not distributed — multi-instance needs shared store); 🟡 token-version revocation on password change (verify); account-enumeration review |
| **AuthZ / multi-tenant** | cross-tenant read/write (BOLA/IDOR) | `tenant_id` scoping + auto-fill from parent case (`app/models/__init__.py` event); tenant-isolation tests — hearings/drafts/fees/diary (`test_tenant_rbac_deep`) + cases/clients/documents incl. download (`test_idor_sweep`) | 🟡 conversations/notifications/workbench not yet in the sweep |
| **API input** | SQLi, XSS, SSRF, mass-assignment | SQLAlchemy ORM (parameterized); Pydantic schemas; security headers + CSP (`app/main.py`) | ⛔ CSRF review; ⛔ SSRF review on any URL-fetching (eCourts/Kanoon clients); CSP uses `unsafe-inline` (frontend inline handlers) |
| **File uploads** (documents, workbench) | malicious PDF/DOCX, path traversal, type confusion, archive bombs, oversized | ✅ extension allowlist + 20 MB cap + tenant-separated storage (`app/services/storage.py`); cross-tenant download blocked (test_idor_sweep) | ⛔ MIME/content sniffing (extension-only can be bypassed by rename); malware scan/quarantine; confirm store isn't web-served |
| **AI answer integrity** | hallucinated law, injected instructions in corpus/uploads/retrieved text | deterministic-first RAG; grounding gate (`safety.enforce_citations`) + act-aware fabrication signal (`citation_guard`); refusal doctrine; soul boot gate | ⛔ prompt-injection test suite; 🔒 claim-to-span entailment (NLI/human) |
| **Secrets** | leakage in logs/repo/output | `.env` gitignored; `detect-secrets` baseline (S0.5); field encryption; preflight blocks deploy without `FIELD_ENCRYPTION_KEY` | 🔒 KMS/secret-manager; key rotation runbook (`docs/security/KEY_ROTATION.md` — S1.6 planned) |
| **Dependencies** | known CVEs, supply chain | blocking `pip-audit` + waivers (S0.3); SBOM (`sbom.json`); lockfile | 🔒 container image scanning |
| **Data at rest** | DB/file/backup theft | `totp_secret` Fernet-encrypted; SQLite backups verified | 🔒 Aurora RDS storage encryption; 🔒 encrypted object storage (S3 SSE-KMS) for files/backups (prod uses local disk today) |
| **Subprocessors** | data sent to third parties; retention/training | providers configurable + no-op when unset; embeddings default to LOCAL ONNX (no external) unless `OPENAI_EMBEDDINGS_KEY` set | ⛔ subprocessor register + vendor retention/training review (see `PRIVACY_DATA_FLOW.md`) |
| **Scheduled jobs** | double/missed execution, unhandled failure | durable idempotent runs (`app/services/scheduler.py`); staleness detection | 🔒 alert channel wiring (OWNER-12) |
| **Infra / deploy** | stale corpus, migration drift, misconfig | fail-closed `release preflight` in `deploy_ec2.sh`; `/healthz` `/readyz` | 🔒 least-priv IAM, private DB networking, TLS, security groups, WAF |

## Top residual risks (for the reviewer)

1. **File-upload hardening** (⛔) — no MIME/malware controls yet; highest-value agent-ownable fix.
2. **IDOR sweep** (⛔) — tenant isolation is enforced + tested in parts, not exhaustively swept.
3. **Prompt-injection resistance** (⛔) — untested against adversarial corpus/upload content.
4. **Prod data-at-rest + secrets** (🔒) — Aurora encryption, KMS, encrypted object storage.
5. **Independent penetration test** (🔒) — not yet performed; this model is the input to it.

**No real client data until G6+G7 sign.** This model is prepared evidence, not a security sign-off.
