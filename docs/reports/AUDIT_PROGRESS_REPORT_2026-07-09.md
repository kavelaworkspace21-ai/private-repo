# Juriscite — Audit & Project Progress Report

**Product:** Juriscite (Master Agent: "Legal Server.AI") — an AI-native legal-practice operating system for Indian advocates and law firms.
**Report date:** 2026-07-09
**Prepared by:** Legal Server.AI build agent, under the V3 Constitution + CLAUDE.md doctrine.
**Verification basis:** repo-verified — every figure below was counted from the working tree or the passing test suite, not estimated.

> **Honesty note (doctrine §13):** this report separates *what is built and tested by the builder* from *what still requires independent human sign-off*. The difference is the whole point. Nothing here is self-certified past a human gate.

---

## 1. Executive summary

Juriscite is **feature-complete and AI-complete for the closed beta**, with a governed billing layer and an Advocate Workbench that is **5 of its 10 sprints live**. The entire system runs behind a hard-wired safety doctrine ("the soul") that the application will refuse to boot without.

| Signal | Status |
|---|---|
| Automated tests | **370 passing, 0 failing** (`pytest`, AI keys blanked) |
| App boots + soul intact | ✅ (`/health` → `soul: intact`) |
| Backend API routers | 22 |
| Database models / tables | 25 |
| Alembic migrations (single head) | 13 |
| Service modules | 18 |
| Frontend pages / JS controllers | 18 / 11 |
| Verbatim statute corpus | 6,457 chunks (ChromaDB) |
| Distinct audited actions | 67 |
| Python LOC (app/) | ~11,600 |
| Production (EC2) | Deployed & healthy — **but new work is HELD** pending Aurora restart + migration |

**Bottom line:** the trustworthy spine is built and green. The remaining risk is concentrated in **human gates** (senior-advocate template/behaviour review; security & privacy review before real client data) and **owner-side infrastructure** (Aurora is stopped; no custom domain/cert yet), not in unbuilt features.

---

## 2. Verification status

- **Full suite: 370 tests, 0 failures**, run with model-provider keys hard-blanked so CI never touches a live LLM (a footgun found and fixed this cycle — see §7).
- Guardrail tests actively enforce doctrine and would fail the build on regression:
  - Alembic head must exactly match the ORM models (no schema drift).
  - UI templates must contain **no prediction/risk-scoring language** (prohibited feature guard).
  - Every AI answer path is citation-gated; banned phrases are scrubbed.
  - Tenant isolation and RBAC are asserted per endpoint.
- **Not yet captured:** a live end-to-end 70B Workbench artifact screenshot — the NVIDIA free tier has been throttled during recent sessions. The generation *paths* are deterministically test-pinned and the UI degrades/recovers correctly; this is an evidence gap, not a known defect.

---

## 3. Module inventory (what exists)

**Practice core:** Auth (JWT + TOTP 2FA, RBAC across advocate / firm_admin / associate / clerk), multi-tenant isolation, Clients, Matters, Documents (versioned, 20 MB + type-whitelisted uploads), Court Diary (hearings, tasks, filing deadlines, reminders via scheduler), Fees.

**AI layer (grounded):** Universal Legal Agent chat (SSE stream, 22 languages), deterministic retrieval (`retrieve_by_section` / title / structured) over 6,457 verbatim chunks, live Indian Kanoon case-law cards (footer only, "good-law unverified" caveat), the Drafting Engine (28 authentic skeletons + provision grounding + DOCX/PDF), and single-prompt chat drafting.

**Advocate Workbench (this pack):** a guided-workflow engine with a state machine (`INTAKE → CONFIRM → GENERATING → COMPLETE / REFUSED`) and per-section grounding gates. **5 of 6 tools live** (see §5).

**Billing & subscriptions (Gate G11, TEST mode only):** plans-as-data, 14-day no-card trial, entitlement metering (research/draft units, 402 on exceed), Razorpay **test-mode** checkout, HMAC-verified idempotent webhooks, GST invoices, seat management, two-click cancellation, trial-expiry downgrade. **No live payments** — gated on human G6/G7.

**Governance & compliance:** consent records (DPDP), data-rights request tracker, misuse reports, audit log (67 distinct actions; every mutation writes a row), policy pack + `/legal` pages, retention jobs, backups, PWA (installable).

---

## 4. Safety doctrine compliance audit

The non-negotiable doctrine (CLAUDE.md §2) and its enforcement:

| Doctrine rule | Enforcement | Verified |
|---|---|---|
| No source, no answer | retrieval gate + `is_answerable` refusal | ✅ tests |
| Every legal claim carries a citation | citation hard-gate on chat + Workbench law sections | ✅ tests |
| Confidence labelling (HIGH/MEDIUM/LOW) | on every answer + artifact | ✅ |
| Every draft `DRAFT_FOR_ADVOCATE_REVIEW` | schema default; no path sets "final" without approval | ✅ tests |
| Banned phrases never appear | `sanitize_answer` scrub, per section | ✅ tests |
| **No outcome prediction, ever** | prohibited-feature guard + Workbench prediction-probe → 422 refusal | ✅ tests |
| Tenant isolation sacred | cross-tenant reads → 404 across all resources | ✅ tests |
| Quotables verbatim (Workbench) | exact-substring + pinpoint gate; paraphrase-as-quote withheld | ✅ tests |
| The soul is supreme | fail-closed boot guard; app refuses to start if doctrine tampered | ✅ |

**Assessment:** the doctrine is enforced *in code with failing tests*, not merely documented. This is the product's core moat and it is holding.

---

## 5. Advocate Workbench — sprint progress

Pack: `docs/sprints/LSAI_ADVOCATE_WORKBENCH_SPRINTS.md` (10 sprints, strict order).

| Sprint | Tool / scope | Status |
|---|---|---|
| WB-00 | Scaffolding: models, `/api/workbench`, nav, hub | ✅ shipped |
| WB-01 | Workflow engine (state machine + all gates) | ✅ shipped |
| WB-02 | Uploads · Chat with Case File · List of Dates · 7-day retention | ✅ shipped |
| WB-03 | Case File Analysis (15 sections, FILE+LAW grounding) | ✅ shipped |
| WB-04 | Deep Research + Legal Memo (Kanoon authorities, both-sides rule) | ✅ shipped |
| WB-05 | Judgment Analyzer (verbatim-quotable gate, Kanoon pick) | ✅ shipped |
| WB-06 | Argument Studio (hearing notes, Judge Mode, counter-args) | ⏳ next |
| WB-07 | Drafting engine parity upgrade + in-app editor | ⬜ pending |
| WB-08 | Exports, Matter linkage, Artifact Library | ⬜ pending |
| WB-09 | Workbench evals + e2e extension + G8 sign-off packet | ⬜ pending |

**Signature achievements of the shipped half:**
- Every workflow is **question-first** — generation is structurally impossible from an unanswered intake.
- Per-section grounding is explicit and enforced: **FILE** (cites the uploaded doc by `[p.N]`), **LAW** (cites retrieved statute), **BOTH**, or authority sections (cite live Kanoon judgments by marker — the model cannot mint a case name).
- The **verbatim-quotable gate** (WB-05) is the strictest in the app: a quoted passage that is not a character-exact substring of the source *on the pinpointed page* is stripped visibly; a section with no surviving quote is withheld.
- Artifacts flow into the existing governed review queue (approve → DOCX/PDF).

---

## 6. Billing & entitlements audit (Gate G11)

- **Mode:** `BILLING_MODE=test`. A live-mode guard (`assert_billing_mode_allowed`) **refuses to process real payments** without an explicit post-G6/G7 approval flag. Verified by test.
- **No dark patterns:** no card for the trial, two-click cancel effective at period end, auto-renew disclosed at checkout, honest refund copy, GST shown exclusive. Pricing copy contains no superiority/outcome claims.
- **Money handled correctly:** amounts stored in integer paise; GST computed exactly (₹999 → ₹179.82 → ₹1,178.82).
- **Trust boundary:** webhooks are believed only after HMAC-SHA256 signature verification; replays are idempotent.
- **RBAC + isolation + audit:** clerk/associate cannot manage billing; a tenant sees only its own subscription/usage/invoices; every mutation is audited.

---

## 7. Security & engineering hardening audit

- **Input boundaries:** size caps on every write surface (chat 8k, draft fields, exports, titles); upload type-whitelist + 20 MB cap; format enums.
- **Session:** 401 handling clears token + redirects; security headers (CSP, HSTS, X-Frame-Options) middleware.
- **Audit coverage:** 67 distinct audited actions — auth, diary, drafts, billing, workbench, conversation-delete, export — every consequential mutation writes who/what/when/tenant.
- **Defects found & fixed this cycle (by our own verification):**
  1. **CI silently called NVIDIA** — PowerShell `$env:X=""` deletes the var and `load_dotenv()` refilled the key. `conftest` now hard-blanks provider keys before import. (This is why a suite once ran 11 min / timed out.)
  2. **PWA service worker served stale JS** — the runtime cache pinned page assets; `VERSION` bumped to `juriscite-v3`, with a documented "bump on every static release" rule.
  3. **File-chat degrades gracefully** on provider failure (returns page-anchored excerpts, never a 500) — verified live against a real NVIDIA timeout.
  4. An orphaned-function bug (`_grounding_for`) and a caveat-detection bug were both caught by new tests and fixed.

---

## 8. Known gaps & risks (honest)

| Item | Type | Impact | Owner |
|---|---|---|---|
| **Aurora (prod DB) is stopped** | Infra | Prod logins fail; Workbench deploy blocked | Owner |
| No custom domain / trusted cert | Infra | Self-signed cert blocks PWA install; prod on IP + self-signed | Owner |
| Live 70B Workbench artifact not captured | Evidence | Paths test-pinned; screenshot pending NVIDIA window | Agent (when quota resets) |
| NVIDIA free-tier throttling | Vendor | Bursty generation timeouts; graceful degrade in place | Owner (paid key / local fallback) |
| Workbench prod tables not yet migrated | Deploy | New `ea94773ec007` migration must run before deploy | Agent (post-Aurora) |
| WB-06 → WB-09 unbuilt | Scope | Argument Studio, editor, artifact library, evals remain | Agent (next sprints) |

---

## 9. Human gates outstanding (never self-certified)

| Gate | What it covers | State |
|---|---|---|
| **G1** | Corpus authenticity (verbatim statute provenance) | OPEN — human |
| **G6** | Privacy review before real client data | OPEN — human |
| **G7** | Security review before real client data | OPEN — human |
| **G8** | Senior advocate signs off template + Workbench prompts & sample outputs | OPEN — human (packet due WB-09) |
| **G11** | Billing go-live | OPEN — depends on G6/G7 |

Public launch remains **locked** until these clear. The build agent will not, and cannot doctrinally, self-certify any of them.

---

## 10. Recommended next actions

**Owner (unblocks the most):**
1. Start the Aurora cluster → unblocks prod logins, the two parked prod cleanup tasks, and Workbench deployment.
2. Decide on a paid model key or local-Ollama fallback so beta advocates don't hit NVIDIA throttling.
3. Purchase a domain when ready → agent runs certbot; enables PWA install.

**Build agent (in-flight):**
1. **LSAI-WB-06 — Argument Studio** (next sprint).
2. Then WB-07 → WB-09; WB-09 produces the **G8 sign-off packet** for the senior advocate.
3. After Aurora is up: `alembic upgrade head` on prod, deploy the Workbench, capture the live 70B artifact evidence.

---

*Build the trustworthy spine first. The AI is only as honest as the sources it can cite. — as of 2026-07-09, the spine is built, green, and gated; what remains is human judgment and the owner's infrastructure.*
