# Juriscite — Gap Matrix (Phase 0)

> **SUPERSEDED IN PART — updated 2026-07-24.** This document is a snapshot of 2026-07-21 and is
> kept as the historical record; the header figures below are stale. Current state: alembic head
> `81665ba86789` (14 migrations) · 26 model modules · 73 test files · **601+ tests passing** ·
> **now a git repo** (baseline `1b7e99b`). Three gaps listed here are closed:
> - Gap 5 *"No git / no commit traceability"* → **CLOSED**. Version control established;
>   `RELEASE.json` pins the commit and preflight blocks dirty/unaudited trees.
> - *"Tenant/consent boundary"* → consent is now **enforced** at the AI boundary across 13
>   handlers (`docs/AI_DATA_BOUNDARY.md`). Cache/job/file propagation remains PARTIAL.
> - Kanoon cost exposure (raised in STATUS, not listed here) → **CLOSED**; `KANOON_ENABLED`
>   defaults off and the dashboard no longer auto-fires the paid call.
>
> Gap 3 *"AI answer integrity not gated"* is **confirmed still open and understated**: the
> citation "hard-gate" only appends a warning and returns the answer. See
> `docs/AUDIT_CLAIM_VERIFICATION_2026-07-24.md`.

**Built:** 2026-07-21 · **Against:** `JURISCITE_REMAINING_GAPS_PROMPT_2026-07-20.md` + `AUDIT_REPORT_2026-07-20.md`
**Verified state (runtime/repo, not the report):** root `D:\MASTER CLAUDE PROJECT FOLDER` · app `0.2.0` ·
corpus fingerprint `2965aab084ff` · alembic head `ea94773ec007` (single) · 13 migration files ·
22 routers / 25 model modules / 62 test files · **516 tests passing / 0 failed** · **not a git repo**.

**Status legend:** `VERIFIED_WORKING` · `PARTIAL` · `BROKEN` · `MISSING` · `GATED_HUMAN` (needs a
named human signature) · `GATED_OWNER` (needs owner money/creds/infra) · `DEFERRED` (by governance/scope) · `PROHIBITED`.

> Truth-order note: this matrix trusts reproducible behavior + repo/tests over the audit narrative.
> The remaining-gaps prompt (2026-07-20) predates two owner actions: **governance framework retired**
> (docs/governance deleted 2026-07-21) and **project relocated off OneDrive to D:** (2026-07-21). Rows
> reflect the current state after both.

---

## Audit claims re-verified

| Claim | Verdict | Evidence |
|---|---|---|
| Fingerprint `2965aab084ff` | CONFIRMED | `python -m app.ai.corpus_updates --fingerprint` |
| 511 tests passing | SUPERSEDED | now **516/0** (Sprint 0 added 5 disk-preflight tests) |
| 50 acts / 8,442 provisions / 8,646 chunks | CONFIRMED | manifest + live chroma count 8,646 |
| 22 routers / 25 models | CONFIRMED | file inventory |
| 14 migrations | CORRECTED | 13 migration files, single head `ea94773ec007` |
| 964 datetime.utcnow warnings | RESOLVED | Sprint 0 S0.1 → now 6 warnings, all third-party |
| Fail-closed soul/prohibited boot gates | CONFIRMED (code) | `app/soul.py`, `app/legal_config.py` still wired in `main.py` |
| Governance constitution is "authority" | OUTDATED | owner retired + deleted `docs/governance/` 2026-07-21 |

---

## P0 — Deployment & release integrity

| Gap | Status | Evidence / note | Owner | Next action |
|---|---|---|---|---|
| Prod EC2 on pre-slice corpus | GATED_OWNER | needs Aurora + deploy | owner | after Aurora; deploy gate rejects stale corpus (Phase 1) |
| Aurora cluster absent | GATED_OWNER | AWS billing owner-only | owner | OWNER action: start cluster (docs/OWNER_QUEUE) |
| Deploy depends on D:-drive Chroma packaging | **PARTIAL → in progress** | chroma_db is DERIVED from versioned `app/legal_corpus/fulltext/*.json`; regenerable by `reseed()` | agent | **Phase 1 tranche now**: RELEASE.json + reproducible reseed-and-verify, no local-disk dep |
| C: disk health / silent reseed no-op | VERIFIED_WORKING | project moved OFF C:; `reseed()` refuses <500 MB; boot warns <2 GB (S0.2); D: ~419 GB free | — | monitored |
| Prod-like PG / HTTPS / DNS / secrets / object-store / monitoring / staging smoke | PARTIAL | PG CI lane exists (S0.4, advisory); rest is owner infra | owner+agent | Phase 2/6/8 evidence; owner infra |
| Encrypted prod backup restored into clean env | PARTIAL | sqlite restore-drill tests exist; production restore unproven | agent | Phase 2: restore drill on PG/object-store |

## P0 — Human gates & real-data prohibition

| Gap | Status | Owner | Next action |
|---|---|---|---|
| G1 corpus authenticity | GATED_HUMAN | senior advocate/editor | packet ready (`docs/legal-review/G1_...`), unsigned |
| G6 privacy · G7 security | GATED_HUMAN | external reviewers | prepare evidence (Phase 6); no real data until signed |
| G8 senior-advocate templates/behaviour | GATED_HUMAN | senior advocate | packet + usability (Phase 7/9) |
| Hallucination/citation legal sign-off | GATED_HUMAN | senior advocate | keep as explicit gate in AI_EVALUATION_REPORT (Phase 4), do not fold away |
| Advocate usability / willingness-to-pay | MISSING → GATED_HUMAN | owner+advocates | Phase 9 beta |

## P1 — AI / RAG quality

| Gap | Status | Next action |
|---|---|---|
| Eval set small (15 safety + 28 retrieval) | PARTIAL | Phase 4: expand advocate-curated set across domains/query-types |
| Failover on liveness probe only | PARTIAL | Phase 4: capability gates (citation/refusal/structured-output) per model |
| MiniLM embeddings not proven optimal | PARTIAL/DEFERRED | Phase 4: benchmark before any embedding/vector migration |
| Claim-level citation entailment / span validation | PARTIAL (Phase 4) | `citation_guard.verify_citations()` resolves every displayed citation (act-aware, catches fabrication/misattribution); **wired into the ai_chat answer path** (`integrity_event()` → logs + `citation_integrity` SSE event, additive to the existing grounding gate, non-blocking). ENTAILMENT (source supports the claim) needs NLI/human. NEXT (browser-gated): UI surfaces the signal; and a validated hard repair-or-refuse gate (needs live-LLM validation of the heuristic) |
| Streamed text before citation validation | UNKNOWN | Phase 4: verify streaming path; block unvalidated final output |
| Prompt-injection resistance (corpus/uploads/facts/retrieved) | PARTIAL | deterministic defenses tested: injected instructions contained as data in the prompt, no-source policy enforced, injection-induced fake citations caught (`test_prompt_injection`, +4). Live-model adversarial evals still LLM-gated |
| Ollama fallback identity/quality/parity | PARTIAL | Phase 4: gate or disable in prod |
| No judgment corpus (Kanoon links unverified) | DEFERRED | C-04 owner decision; keep out of grounding |

## P1 — Corpus correctness & currency

| Gap | Status | Next action |
|---|---|---|
| Constitution Schedules 1-6/8/9/11/12 missing | PARTIAL/DEFERRED | owner+legal: required-for-beta decision; else disclose + refuse (Phase 5) |
| ITA-1961 heading-grade | GOVERNED | flagged historical; surface in results/citations (Phase 5) |
| Amendment dates act-level (not provision) | DEFERRED | disclose limitation; refuse date-specific precision (Phase 5) |
| ITA-2025 drift errors (WAF) | PARTIAL | manual-verify fallback w/ last_verified_at + reviewer (Phase 5) |
| IT Rules 2026 drift skipped (landing page) | PARTIAL | same manual-fallback record (Phase 5) |
| IPC `354E` duplicate, silent first-wins | PARTIAL | explicit anomaly record + corpus-report warning (Phase 5) |
| Limitation low-num Schedule article vs body section | PARTIAL | intent detection + disambiguation + separate-path tests (Phase 5) |
| "Acquisition queue empty" ≠ corpus complete | DOC | clarify in CORPUS_LIMITATIONS (Phase 5) |

## P1 — Runtime architecture & durability

| Gap | Status | Next action |
|---|---|---|
| APScheduler in-process (multi-worker double/again) | VERIFIED_WORKING (Phase 3) | `run_tracked_job` DB unique-claim = exactly-once per slot across workers; job runs persisted; `stale_jobs()` detects missed. Alert-channel wiring = GATED_OWNER (OWNER-12) |
| ChromaDB local sqlite PersistentClient | PARTIAL | Phase 3: document single-instance constraint or benchmark; no pgvector migration without measured need |
| Durable object storage for files/backups | MISSING | GATED_OWNER infra; Phase 6 (encrypted private bucket) |
| Tenant/consent boundary across caches/jobs/files | PARTIAL | Phase 6 verification |
| 964 datetime.utcnow warnings | VERIFIED_WORKING (RESOLVED) | S0.1; 6 third-party warnings remain (FastAPI on_event, chromadb asyncio) |

## P1 — Security & privacy evidence

| Gap | Status | Next action |
|---|---|---|
| Independent security approval (G7) | GATED_HUMAN | Phase 6 evidence pack |
| Dependency scanning | VERIFIED_WORKING | S0.3 blocking pip-audit + waivers |
| Secret scanning | VERIFIED_WORKING | S0.5 detect-secrets baseline |
| Security headers / CSP | PARTIAL | present in `main.py` (CSP w/ unsafe-inline); Phase 6 tighten + CSRF |
| IDOR / cross-tenant sweep | PARTIAL (verified) | isolation CONFIRMED for hearings/drafts/fees/diary (`test_tenant_rbac_deep`) + cases/clients/documents incl. download (`test_idor_sweep`); conversations/notifications/workbench still to sweep |
| Pentest / container scan / malware scan / CSRF | MISSING | Phase 6 (pentest = external; malware/MIME sniffing = agent-ownable) |
| Upload hardening | MOSTLY DONE | extension allowlist + 20MB cap + tenant-separated storage + **magic-byte content sniffing** (`storage.py`, +10 tests) — renamed/spoofed files rejected; only external malware-scan/quarantine remains (owner infra) |
| Deletion/export propagation (PG/files/Chroma/caches/backups/logs) | PARTIAL | data_rights exists; propagation unverified (Phase 6) |
| Vendor retention/training policies (NIM/email/Razorpay/…) | MISSING | Phase 6 SUBPROCESSORS/PRIVACY_DATA_FLOW |
| Sensitive facts/tokens never in logs/analytics/SW cache | PARTIAL | Phase 6 verification |

## P1 — UI / UX / a11y / PWA

| Gap | Status | Next action |
|---|---|---|
| Design-system audit / Executive Dark consistency | MISSING | Phase 7 (audit-first) |
| WCAG 2.2 AA / keyboard / screen-reader / zoom / contrast | MISSING | Phase 7 axe + manual |
| Responsive 360/768/1440/wide + visual regression | MISSING | Phase 7 |
| State coverage (loading/empty/error/offline/refusal/disabled) | PARTIAL | Phase 7 |
| Matter-centric context continuity | PARTIAL | Phase 7 |
| PWA offline stale-content messaging | PARTIAL | Phase 7 |
| Capacitor native release-ready | DEFERRED | keep deferred unless separately approved |

## P2 — Ops / product / paid launch

| Gap | Status | Next action |
|---|---|---|
| Observability / SLO / alerts / dashboards | PARTIAL | request-ID + Sentry hook exist; Phase 8 metrics/SLO |
| Load / failure-injection / rollback / runbooks | MISSING | Phase 8 |
| Beta onboarding / support / analytics / WTP | MISSING | Phase 9 |
| Razorpay live mode | GATED (correct) | blocked until G6/G7 + owner |
| eCourts read-only feature-flagged | VERIFIED_WORKING | existing; never scrape |
| Kanoon links unverified, outside grounding | VERIFIED_WORKING | existing |

---

## Five highest-risk remaining gaps (with evidence)

1. **No reproducible release artifact; deploy leans on local D: Chroma** (P0). Evidence: corpus lived only as a
   local Chroma dir; no manifest pins the shipped fingerprint; deploy can't detect a stale corpus. → **Phase 1 (now).**
2. **Aurora/prod deployment unproven** (P0, GATED_OWNER). Evidence: prod EC2 on pre-slice corpus; no Aurora. → Phase 2 engineering + owner action.
3. **AI answer integrity not gated** (P1). Evidence: no claim-level citation entailment; streaming-vs-validation order unknown; no prompt-injection tests. → Phase 4.
4. **Human gates all unsigned + no real-data guard proven end-to-end** (P0, GATED_HUMAN). → prepare G1/G6/G7/G8 evidence (Phases 4/6/7).
5. **No git / no commit traceability** (P0-adjacent). Evidence: `git rev-parse` fails. Can't pin the "audited commit" or bisect. → recommend `git init` (owner decision) + record a synthetic release id meanwhile.

## Not started here (require owner/human before agent work is meaningful)
G1/G6/G7/G8 signatures · Aurora start · DNS/TLS · production secrets · live Razorpay · C-04 judgment corpus · native app scope.
