# Owner Queue

Items that an agent cannot complete (money, credentials, signatures, third-party accounts,
AWS, or deliberate human decisions). The sprint sheet's §13 is the master list; this file is
what the build work has actually surfaced and hands off. Newest sprint on top.

---

## From the corpus flag sweep (2026-07-29)

- **RESOLVED 2026-07-30 — schedule-aware parsing built.** NDPS (+106 psychotropic
  substances), Specific Relief (+5 infrastructure categories), Partnership (+9 Schedule I
  fee entries) — 120 entries that were previously dropped. Every body section is
  byte-identical and no id repeats, both checked against the shipped corpus. Ids use the
  Constitution's `Sch7.L1.*` precedent so a schedule entry can never occupy a section
  number, which is the collision that cost ten sections of law in arbitration, CrPC and IBC.

  **This entry previously listed Commercial Courts (Order XV-A) as a fourth act, and that
  was WRONG.** `article_schedule: "bare"` has always parsed that act, and better than the
  generic parser would: the shipped corpus carries `Sch.1` "Disclosure and discovery of
  documents", `Sch.2` "Discovery by interrogatories", `Sch.3` "Inspection" — Order XV-A
  split rule by rule. The claim that its case-management content was missing was inherited
  and repeated for months without anyone opening the file. It surfaced only because a
  body-integrity check failed and the failure was diagnosed rather than assumed to be the
  new code's fault.

  Worth keeping as a caution: a queue item asserting something is MISSING is a claim about
  the corpus, and this project has now been wrong about that in both directions — content
  believed present that was amendment text (arbitration s.16, CrPC s.44, IBC s.6), and
  content believed missing that was there all along (Order XV-A). Verify before acting on
  either.

- **RESOLVED 2026-07-29 — reseed had no crash safety.** It deleted the live collection
  first and embedded for minutes, so any interruption left a truncated index that still
  answered queries with most of the law missing. Three occurrences (2026-07-20 disk-full,
  -25 concurrent, -29 killed process leaving 1,200 of 8,704 chunks). Now builds into a
  separate collection and swaps by rename, with a lock, a shrink check and orphan recovery.

## From the pre-deploy hardening review (2026-07-25)

- **Rate limiting is per-process — do NOT scale horizontally yet.** Buckets live in the app
  process's memory, so N instances behind a load balancer multiply every limit by N (5
  login attempts/min becomes 5N), and a restart clears them entirely. The limits are correct
  on a single node, which is the current deployment. **Before adding a second instance or an
  autoscaling group, move the buckets to a shared store (Redis).** `REDIS_URL` already exists
  in the compose file; the limiter does not use it.
- **Set `ENVIRONMENT=production` on the server.** Several protections key off it: the secret
  boot gate, the database TLS check, and disabling the API docs. It is *safe* if you forget
  (unset is treated as production, so it fails closed), but set it explicitly so the intent
  is visible in the deployment config rather than inferred from a default.
- **`DATABASE_URL` must carry `?sslmode=require`** (or `verify-full` with a CA bundle) for
  Aurora. Without it libpq defaults to `prefer`, which silently downgrades to an
  UNENCRYPTED connection if the server does not offer TLS — client matter data would cross
  the network in the clear with no error. The app now refuses to boot in production without
  it, so this is enforced rather than advisory.
- **CSP still allows `'unsafe-inline'` for scripts.** The frontend uses inline event
  handlers and inline `<script>` blocks, so tightening this is a real frontend refactor
  (move handlers to addEventListener, add nonces), not a config change. Worth doing before
  G7; it is the weakest part of an otherwise complete header set.

## From the Vision-Alignment Program — Phase 1 consent policy (2026-07-24)

Consent enforcement itself was **not** put to you — the prompt is explicit that for a legal
product handling client data the safe default is enforcement, so it is enforced (see
`docs/AI_DATA_BOUNDARY.md`). What genuinely needs a human decision is the *wording and shape*
of the policy, which is a counsel question:

- **Final consent wording** for AI processing. The gate currently keys off the existing
  privacy-policy consent. The text an advocate accepts should say plainly that matter text and
  uploaded documents are sent to a third-party model. Needs G6 counsel sign-off.
- **Purpose granularity.** One acceptance currently authorises all AI processing. DPDP favours
  specific, purpose-limited consent — e.g. separating "statutory research" (no client data)
  from "send my client's matter/documents to an external model". Building it is engineering;
  deciding the purposes is policy. **This is the largest remaining Phase 1 item.**
- **Whose consent.** The advocate consents; their *client* — whose data is actually in the
  prompt — is not a party to it. Whether the advocate's professional authority covers this, or
  a client-facing notice/consent is required, is a legal question I cannot answer.
- **Re-consent policy.** Bumping `PRIVACY_VERSION` currently invalidates prior consent and
  forces re-acceptance. Confirm that is the behaviour you want on every policy edit, or whether
  only material changes should re-trigger it.

## From the Vision-Alignment Program — Phase 0 (2026-07-24)

- **ROTATE THE INDIAN KANOON API KEY.** `INDIAN_KANOON_API_KEY` in the local `.env` is a live
  **paid** key. It is correctly gitignored and was verified **absent** from the baseline commit —
  but I displayed it in plaintext in the 24 July session while tracing the Kanoon call path (my
  error; I should have matched on the variable name only). Treat it as exposed-to-transcript and
  rotate it at Indian Kanoon. Owner-only. Nothing else was exposed — `.env`, `*.pem`, token temp
  files, local databases and `data/uploads/` are all excluded from version control and verified
  absent from the commit.
- **`git init` — DONE, no longer an owner decision.** The vision-alignment prompt (Phase 0)
  explicitly authorised it, so it was taken: baseline commit `1b7e99b`, 437 files, secrets scanned
  first. This supersedes the "Decide on `git init`" item below.
- **Set an upstream remote (optional).** The repo is local-only. If you want off-machine history
  (and a rollback that survives a disk failure), create a **private** repo and push. Do not make it
  public — the corpus fulltext and draft templates are versioned. Owner decision; I have not
  created or pushed to any remote.

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
- ~~**Decide on `git init`.**~~ **RESOLVED 2026-07-24** — authorised by the vision-alignment
  prompt and done (baseline `1b7e99b`; release pinned at `af1774d`). See the Phase 0 section
  at the top.
- **Aurora / prod infra** (unchanged, still blocking Phase 2): start the cluster; provide
  trusted HTTPS + DNS, restricted networking, least-privilege IAM, KMS/secret-manager, and
  durable encrypted object storage for uploads/backups. The release artifact is now reproducible
  (Phase 1); the infrastructure it deploys onto is the owner track.

## From Sprint 0 — Baseline Hygiene (2026-07-21)

### Decisions / follow-ups the agent intentionally did NOT auto-apply
- ~~**Promote the Postgres CI suite to blocking.**~~ **DONE 2026-07-30.** `continue-on-error`
  removed; both `alembic upgrade head` and the full suite are blocking on real `postgres:16`.
  The first genuine run (#10) returned **764 passed, 1 skipped, 17 errors** — and every error
  was in fixture setup, not test logic. There were no SQLite-only test assumptions to fix; the
  harness itself was the problem (abandoned scheduler jobs + leaked sessions deadlocking
  against `TRUNCATE`). Fixed 2026-08-04; see `docs/POSTGRES_MIGRATION_AUDIT.md`.
- **GitHub Actions are running on a deprecated Node runtime.** CI run #20 annotated: "Node.js
  20 is deprecated. The following actions target Node.js 20 but are being forced to run on
  Node.js 24: `actions/cache@v4`, `actions/checkout@v4`, `actions/setup-python@v5`,
  `actions/upload-artifact@v4`." Nothing is broken — GitHub is force-upgrading the runtime —
  but the forcing will not last forever. **Action (agent, low priority):** bump each action to
  the major version that targets Node 24, one commit, and confirm the annotation disappears.
- **`actions/cache` no longer saves on a failed job.** `save-always: true` was removed from
  both cache steps in `.github/workflows/ci.yml` — GitHub deprecated it ("does not work as
  intended and will be removed"), so it was doing nothing while reading as solved. The
  consequence is real: a job that fails before the post-step never populates the vector-index
  cache, so a persistently-failing lane keeps paying the full ~15-25 min cold embedding build.
  **Action (agent, low priority):** replace with a separate `actions/cache/restore` at the top
  and `actions/cache/save` with `if: always()` at the end.
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
- **OWNER-14 — Uploaded client files have NO backup at all.** Found in S4, 2026-08-04. This is
  distinct from (and more severe than) B3 "restore-test the RDS backup path": B3 is an
  untested backup, this is the **absence** of one. Document *rows* live in PostgreSQL and are
  covered by Aurora PITR. Document *bytes* live on local disk under
  `data/uploads/<tenant_id>/` — `app/services/storage.py` is filesystem-only, there is no
  `boto3` and no bucket anywhere in `app/`, and its docstring names S3 as a future swap that
  has not happened. Restore the database alone and every document row points at a file that is
  not there; the UI still lists the document and the bytes are gone. **Nothing in the database
  is wrong, so no database-level check can see it** — `scripts/verify_restore.py` walks the
  filesystem for exactly this reason. Losing `chroma_db/` is an outage (derived, rebuildable);
  losing `data/uploads/` is data loss. **Action (owner, before any real client data):** put
  `data/uploads/` on durable storage (EFS with backup, or complete the S3 swap the code was
  designed for), or back it up on the database's schedule and retention. See
  `docs/BACKUP_AND_DR.md` §1.
- **OWNER-13 — The GitHub repo is still PUBLIC.** Verified against the API on 2026-08-04:
  `visibility: public`, `private: false`. It was set public deliberately so CI logs could be
  read without auth, and the intent afterwards was to set it back — that has not taken effect.
  While public it exposes `THREAT_MODEL.md`, `docs/POSTGRES_MIGRATION_AUDIT.md` and the
  known-defect list in `docs/FINAL_AUDIT_2026-07-31.md`. **Action:** Settings → General →
  Danger Zone → Change visibility → Private. Note this makes Actions logs unreadable without
  `gh auth login`, so do it after the current CI work settles.

### Security note (informational — handled in-code, no action required)
- pip-audit is now a **blocking** CI gate. Two vulnerabilities with no upstream fix are waived
  with written justification in `security/pip-audit-waivers.txt`: `ecdsa` (unused — JWTs use
  HS256) and `chromadb` (ingests only our verified corpus). Two others were **fixed** by pinning
  `pillow>=12.3.0` (20 CVEs) and `pydantic-settings>=2.14.2`. Re-review the waivers when those
  upstreams publish fixes.
