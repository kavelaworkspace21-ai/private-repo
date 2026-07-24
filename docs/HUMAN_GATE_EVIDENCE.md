# Human-Gate Evidence Index

**Purpose:** for each gate, what it certifies, the evidence that ALREADY EXISTS (with pointers),
what is still MISSING, the named human who must sign, and the next action. The agent prepares
evidence; it **must not** sign or fabricate any gate. State as of 2026-07-22 · app `0.2.0` ·
fingerprint `2965aab084ff` · 548 tests passing.

> No real client data and no live billing until **G6 + G7** are signed.

---

## G1 — Legal corpus authenticity · `BLOCKED_PENDING_HUMAN`

**Certifies:** the corpus is authentic, verbatim, official-source statutory text with honest
disclosure of limits.

**Evidence that exists:**
- `docs/legal-review/G1_CORPUS_AUTHENTICITY_PACKET.md` (READY-UNSIGNED).
- Per-act provenance: source URL + SHA-256 + page + fetch date (`corpus_updates.corpus_manifest()`).
- Fingerprint `2965aab084ff` (hashes source SHA + parsed content); CLI `python -m app.ops.release status`.
- **Structural anomalies surfaced, not hidden:** `corpus_updates.corpus_anomalies()` flags IPC 354E
  (two provisions, one number) as `PENDING_LEGAL_REVIEW`.
- `docs/CORPUS_LIMITATIONS.md` — every known limitation (354E, ITA-1961 heading-grade, act-level
  amendment dates, missing Constitution Schedules, drift currency) with disclosure + tests.
- Deterministic parser (no LLM in ingestion); 40+ landmark-content checks.

**Missing / reviewer decides:** canonical treatment of IPC 354E; whether missing Constitution
Schedules are required for beta; ITA-1961 historical-only acceptance.
**Named human:** senior advocate / legal editor. **Next:** review packet + anomalies, sign.

## G6 — Privacy / DPDP · `BLOCKED_PENDING_HUMAN`

**Certifies:** DPDP-aligned consent, rights, retention, and breach handling.

**Evidence that exists:** data-rights router (access/erasure); prompt **log-redaction**
(`data_boundary.redact_for_log`); embeddings default to **local ONNX** (nothing external);
retention/purge jobs (durable — Phase 3); audit coverage + retention tests; `totp_secret` field
encryption at rest (`app/db/crypto.py`); `docs/PRIVACY_DATA_FLOW.md` (data map + subprocessors);
`docs/INCIDENT_RUNBOOK.md` (DPB/CERT-In templates).

**Missing / verified gaps:** **⚠ consent (`ConsentRecord`) is NOT wired into the AI path** — no
purpose-consent check before an LLM call (must be enforced + tested for G6); deletion/export
propagation verified across PG/files/Chroma/backups/logs; correction + grievance + nominee rights;
retention schedule per model; vendor retention/training-policy confirmations (NIM/email/Razorpay).
**Named human:** privacy reviewer / counsel. **Next:** wire+test consent enforcement (agent), owner
engages reviewer.

## G7 — Security · `BLOCKED_PENDING_HUMAN`

**Certifies:** independent approval of the security posture.

**Evidence that exists:**
- Fail-closed boot gates (soul + prohibited-features); bcrypt + TOTP 2FA; JWT.
- **Dependency scanning:** blocking `pip-audit` in CI + documented waivers (S0.3).
- **Secret scanning:** `detect-secrets` baseline (S0.5).
- Security headers + CSP, `X-Frame-Options`, HSTS, nosniff (`app/main.py`).
- Tenant-isolation tests (`test_child_tenant`, `test_tenant_rbac_deep`); SBOM (`sbom.json`).

**Missing:** `docs/THREAT_MODEL.md`; independent penetration test; CSRF/IDOR/SSRF/upload-malware
sweeps; least-privilege IAM + KMS + private DB networking evidence (owner infra). **Named human:**
external security reviewer. **Next:** owner engages pentest; agent prepares threat model + more
API-level abuse tests.

## G8 — Senior-advocate templates, AI behaviour, usability · `BLOCKED_PENDING_HUMAN`

**Certifies:** the drafting templates and AI behaviour are safe and useful in real practice.

**Evidence that exists:** 28 draft skeletons (`templates/drafts/`); deterministic eval set (15 safety
+ 29 retrieval cases incl. Limitation disambiguation, ITA-2025, repeal flags); refusal doctrine +
"DRAFT_FOR_ADVOCATE_REVIEW" labelling; provenance chips.

**Missing:** `docs/AI_EVALUATION_REPORT.md` with the expanded advocate-curated set + claim-level
citation entailment; moderated usability sessions; willingness-to-pay. **Named human:** senior
advocate. **Next:** run the 30-min scripted demo + usability; sign templates + behaviour.

## Hallucination / citation legal sign-off · `BLOCKED_PENDING_HUMAN`

Keep as an EXPLICIT gate (do not fold into G8 silently). Evidence: deterministic citation/refusal
evals; provenance-verified retrieval; repeal flags. Missing: claim-level entailment + calibrated
thresholds (Phase 4). **Named human:** senior advocate reviews the results before this is signed.

---

## Owner gates (not human-review; owner authorisation) — `BLOCKED_PENDING_OWNER`

Aurora start · production secrets (incl. `FIELD_ENCRYPTION_KEY`) · DNS/TLS · live Razorpay
activation · e-SCR/judgment-corpus decision C-04 · native-app / citizen-scope expansion.
See `docs/OWNER_QUEUE.md`.

**Nothing above is signed.** Do not represent Juriscite as production-ready or launch-ready while
any gate on this page is open.
