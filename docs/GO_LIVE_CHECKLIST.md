# Go-Live Checklist (Supervised Advocate Beta)

Status as of 2026-07-22 · app `0.2.0` · fingerprint `2965aab084ff` · migration head `81665ba86789`
· **548 tests passing / 0 failed**. Legend: ✅ done · 🟡 partial/evidence-prepared · 🔒 gated
(owner/human) · ⛔ not started.

This is the checklist the launch decision walks. **Public paid launch is a separate, later
milestone** (adds signed human gates, beta remediation, live-billing approval, SLO evidence, WTP).

## Engineering readiness (agent-ownable)

- [✅] Full suite green (SQLite) — 548/0.
- [🟡] Full suite green on **Postgres** — CI `test-postgres` lane exists; suite step advisory until a
      first green CI run confirms no more SQLite-only assumptions (no local Docker to self-certify).
- [✅] Reproducible release artifact — `RELEASE.json` + `python -m app.ops.release preflight` (fail-closed).
- [✅] Corpus fingerprint verified at boot/deploy; stale corpus refused (preflight).
- [✅] Soul + prohibited-features boot gates untouched and passing (byte-identical doctrine).
- [✅] Datetime warnings resolved (964 → 6 third-party); DTZ lint gate.
- [✅] Supply chain: lockfile, SBOM, blocking pip-audit (+ waivers), secret scan, pre-commit.
- [✅] Disk preflight (boot warn <2 GB; reseed refuses <500 MB).
- [✅] Scheduler durable + idempotent (exactly-once per slot across workers); job-run persistence;
      staleness detection.
- [✅] Health/readiness — `/healthz`, `/readyz`, admin `/status`.
- [✅] Corpus edge cases governed (IPC 354E anomaly visible; Limitation Article/Section
      disambiguation; drift `currency` = UNVERIFIED until human sign-off).
- [✅] Runbooks: deployment, backup/restore (backup drill executed).
- [⛔] `THREAT_MODEL.md`, `PRIVACY_DATA_FLOW.md`, `INCIDENT_RUNBOOK.md`, `AI_EVALUATION_REPORT.md`,
      `ACCESSIBILITY_REPORT.md`, `BETA_PLAN.md` — to prepare (agent-ownable, evidence docs).
- [⛔] Expanded AI eval + claim-level citation entailment; prompt-injection tests (Phase 4).
- [⛔] a11y (WCAG 2.2 AA) / responsive / PWA / visual-regression — needs the app in a real browser.
- [⛔] Load / outage / rollback drills on prod-like infra.

## Owner infrastructure — 🔒 BLOCKED_PENDING_OWNER

- [🔒] Aurora cluster started, in-VPC; `DATABASE_URL` in the box `.env` (secret store).
- [🔒] `FIELD_ENCRYPTION_KEY` set in prod (preflight blocks deploy without it — dev `.env` lacks it).
- [🔒] Trusted HTTPS + DNS; restricted security groups; least-privilege IAM; KMS/secret manager.
- [🔒] Durable encrypted object storage (S3 SSE-KMS) for uploads/backups; restore drill on prod-like infra.
- [🔒] Error-tracker + alert channel (OWNER-12) wired to `stale_jobs()` / failures.
- [🔒] Staging environment to run the deploy + backup runbooks end-to-end.
- [🔒] `BILLING_MODE` stays `test`; Razorpay live approval only at the launch meeting.
- [🔒] `git init` decision (no VCS today = no rollback/commit-pin/history).

## Human gates — 🔒 BLOCKED_PENDING_HUMAN (see `HUMAN_GATE_EVIDENCE.md`)

- [🔒] G1 corpus authenticity — packet ready, unsigned.
- [🔒] G6 privacy · G7 security — evidence partial; external reviewers.
- [🔒] G8 senior-advocate templates/behaviour/usability.
- [🔒] Hallucination/citation legal sign-off (explicit, not folded into G8).

## Beta operations — ⛔ / 🔒

- [⛔] `BETA_PLAN.md`: onboarding, support, incident escalation, feedback capture, data-handling.
- [🔒] Recruit 5–10 advocates; signed beta agreements; **synthetic/approved data only** (pre-G6/G7).
- [⛔] Metrics: task completion, citation trust, drafting usefulness, retention, WTP (privacy-safe).

---

**Single next owner action:** set `FIELD_ENCRYPTION_KEY` in the prod secret store (it's the one item
blocking a clean prod `preflight`), then start Aurora. **Do NOT** flip `BILLING_LIVE_APPROVED` or admit
real client data until G6 + G7 are signed.
