# Owner Queue

Items that an agent cannot complete (money, credentials, signatures, third-party accounts,
AWS, or deliberate human decisions). The sprint sheet's §13 is the master list; this file is
what the build work has actually surfaced and hands off. Newest sprint on top.

---

## AGENT AWS ACCESS REVOKED (owner-directed 2026-07-22)

Owner instruction: *"cut your access to any Amazon AWS service we are currently using."* Done at the
agent level; **AWS-side revocation is owner-only and still open.**

**Revoked / verified (agent side):**
- **20 standing permission grants removed** from `.claude/settings.local.json` (141 → 121, 0
  remaining) — every pre-approved `ssh`/`scp` to `ubuntu@100.31.212.252` using `legal.pem`, plus the
  key copy/chmod commands. Backup: `.claude/settings.local.json.pre-aws-revoke.bak`.
- **No AWS credentials available to the agent:** no `AWS_*` env vars, no `~/.aws` profile, no `aws`
  CLI installed. No user-level Claude settings, so no grants outside this project.
- **The app itself makes no AWS API calls** — no `boto3`/`botocore` in requirements. Active
  `DATABASE_URL` is local SQLite; the Aurora URL in `.env` is commented out (inactive).

**Still OWNER-ONLY (I cannot do this — this is what real revocation requires):**
- The EC2 key `C:\Users\prith\Downloads\legal.pem` **still exists and still works**. Removing my
  permission grants does NOT invalidate the key. For true revocation: rotate/replace the EC2 key
  pair in the AWS console and/or tighten the instance security group.
- The commented Aurora connection string (with credentials) remains in `.env` — inactive, but
  present in the file. Consider a secret manager instead.
- **Deliberately NOT deleted:** `legal.pem` and the Aurora URL are YOUR credentials/config —
  removing them could lock you out of your own server or lose the prod connection string.

## From the Remaining-Gaps Program — Phase 3 (2026-07-21)

- **Choose the alert channel for scheduled jobs (OWNER-12).** Phase 3 added job-run persistence
  + `stale_jobs()` detection (missed reminders/backups/drift), but routing an alert (email/Slack
  webhook) needs an owner decision on the channel + credentials. Detection + structured error logs
  are in place; wiring the notification is the remaining step.
- **Resolve the `misuse_reports.created_at` nullability drift.** Alembic autogenerate flagged that
  the model declares `created_at` NOT NULL while the migration head has it nullable. Left out of the
  Phase 3 migration (unrelated + altering to NOT NULL needs a check that no existing rows are null).
  Decide: either relax the model to nullable, or write a data-checked migration to enforce NOT NULL.

## From the Remaining-Gaps Program — Phase 0/1 (2026-07-21)

- **`FIELD_ENCRYPTION_KEY` — LOCAL dev key set 2026-07-22 ✅; PROD key still owner action.**
  A random independent Fernet key was generated and written to the local `.env` (gitignored,
  not committed); the dev/prod-mode preflight now passes and the encryption round-trip works.
  **Still owner:** provision a SEPARATE strong key in the production **secret manager** (KMS /
  AWS Secrets Manager — not a `.env` file) and set it BEFORE any real client data. Note: this is
  the right time (pre-G6/G7, no real data), so nothing needs re-encrypting. Key rotation later
  requires decrypt-then-re-encrypt of `totp_secret` rows (see `app/db/crypto.py`).
- **Decide on `git init`.** The project is not a version-controlled repo, so there's no commit
  to pin the "audited release", no history, and no safe rollback/bisect. The remaining-gaps
  prompt assumes an "exact audited commit". Recommend initializing git (the folder is no longer
  OneDrive-synced after the D: move, removing the earlier concern). Owner decision — not taken
  by the agent.
- **Aurora / prod infra** (unchanged, still blocking Phase 2): start the cluster; provide
  trusted HTTPS + DNS, restricted networking, least-privilege IAM, KMS/secret-manager, and
  durable encrypted object storage for uploads/backups. The release artifact is now reproducible
  (Phase 1); the infrastructure it deploys onto is the owner track.

## From Sprint 0 — Baseline Hygiene (2026-07-21)

### Decisions / follow-ups the agent intentionally did NOT auto-apply
- **Promote the Postgres CI suite to blocking.** The new `test-postgres` job runs the full
  suite against a real `postgres:16` (via a DB-configurable test harness), but its suite step
  is `continue-on-error: true` because it could not be verified locally (no Docker/Postgres on
  the dev box). `alembic upgrade head` on Postgres IS blocking. **Action:** after the first CI
  run on a push, confirm the Postgres suite is green, then delete the `continue-on-error: true`
  line in `.github/workflows/ci.yml` to make it blocking. If it's red, the failures are real
  SQLite-only assumptions to fix.
- **One-time repo-wide `ruff format`.** 154 files would be reformatted. Deferred so it doesn't
  bury the Sprint-0 diff (and there is no git here to isolate it into its own commit). The
  pre-commit `ruff-format` hook already formats files as they're touched. **Action (optional):**
  run `ruff format .` as a single formatting-only change when convenient, then commit alone.
- **App timezone (`Asia/Kolkata`) for calendar dates.** 15 `date.today()` calls (diary,
  reminders, court cause-lists, notifications) use the machine's local date. For an India-only
  tool that should be explicit IST, not server-local/UTC. Ruff DTZ011/DTZ012 are currently
  ignored for this reason. **Action:** decide on an explicit app timezone; then these become a
  small, correct sweep (tracked, not urgent).

### Standing owner items this work depends on (see sheet §13 for the full list)
- **OWNER-1 — Clean C: drive.** Still chronic. Sprint 0 added a boot warning + a hard reseed
  refuse below 500 MB, but the box genuinely needs space freed (corpus already moved to D:).
- **OWNER-2 — Start the Aurora cluster.** Needed to actually exercise the Postgres path beyond
  CI and to deploy the current corpus. AWS billing is owner-only.
- **OWNER-12 — Error-tracker + alert channel choice** (GlitchTip/Sentry, email/Slack webhook) —
  feeds Sprint 5 observability.

### Security note (informational — handled in-code, no action required)
- pip-audit is now a **blocking** CI gate. Two vulnerabilities with no upstream fix are waived
  with written justification in `security/pip-audit-waivers.txt`: `ecdsa` (unused — JWTs use
  HS256) and `chromadb` (ingests only our verified corpus). Two others were **fixed** by pinning
  `pillow>=12.3.0` (20 CVEs) and `pydantic-settings>=2.14.2`. Re-review the waivers when those
  upstreams publish fixes.
