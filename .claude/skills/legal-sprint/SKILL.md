---
name: legal-sprint
description: Execute one LegalServer.AI build sprint end-to-end with the Master Agent's discipline (verify → plan → build → test → prove → record → report). Use when implementing the next STATUS.md item, a feature, a fix, or any code change to this project. Enforces the safety doctrine, tests, and the resumable handoff.
---

# Legal Sprint — one unit of work, done right

Run this loop for every change. Keep changes small, correct, auditable. Prefer simple over clever.

## Step 1 — Verify (don't trust, check)
- Read `docs/STATUS.md` → take the `Next action`. Confirm the real state in the repo (don't
  assume from reports — the repo is truth).
- Confirm the server runs and the baseline suite count (currently 85): `python -m pytest -q`.

## Step 2 — Plan
State the goal in one line and its **"done when"** (the acceptance check). Identify which
Article V agent-role you're acting as (Legal Source / Research / Citation / Drafting / Practice /
Tenancy / Security / Privacy / Infra / QA) and respect that role's hard limit.

## Step 3 — Build
Write the smallest correct change. Mandatory invariants for any data/endpoint:
- Carries `tenant_id`; every mutation writes an `AuditLog` row; documents write a `DocumentVersion`.
- Writes go through `require_matter_write` (RBAC); reads are tenant-scoped (cross-tenant → 404).
- Secrets only via `.env` (gitignored) — never committed.
- AI paths: retrieve → ground → cite → confidence label; abstain with no source; banned-phrase
  safe; drafts `DRAFT_FOR_ADVOCATE_REVIEW`; human-verified data flagged (e.g. `advocate_approved:false`).

## Step 4 — Test (every sprint ships tests)
Add, as applicable: happy-path · auth-required (401) · validation (422) · RBAC (403) ·
tenant-isolation (cross-tenant 404) · and for AI: citation/abstention/banned-phrase/confidence.
Run the **full** suite; keep the end-to-end advocate journey green. Never skip or silently
disable a failing test; report the real pass count.

## Step 5 — Prove
Show concrete evidence: test output (new count vs previous), a live curl/SSE result, a fired
reminder, a cited answer, a 429, etc. Restart the server and hit `/health` after backend changes.

## Step 6 — Record (makes the work resumable)
- Update `docs/STATUS.md`: tick the item, set the new `Next action`, bump the test count, append a
  dated session-log entry (files changed · tests · evidence · gates touched · known gaps · next).
- Update the `project-current-status` memory.

## Step 7 — Report
Close with: files changed · tests run (real pass count vs previous) · evidence it works ·
gates touched · known gaps/risks · next step. Be honest about caveats and anything needing a human.

## Stop-the-line
If you hit a broken e2e journey, cross-tenant leak, uncited answer, unapproved final draft, or a
committed secret — halt feature work and fix it first.
