# Backup & Restore Runbook

**Scope:** database backups + verified restore for Juriscite. Grounded in `app/services/backup.py`
and an **executed drill** (evidence below), not narrative. Prod object-storage + Aurora PITR steps
are `GATED_OWNER` and marked as such.

## Backend-aware behaviour (`app/services/backup.py`)

| Backend | Backup mechanism | Status recorded |
|---|---|---|
| **SQLite** (local/dev) | consistent online copy via SQLite's backup API, rolling retention (`BACKUP_KEEP`) | `success` + file path + size |
| **PostgreSQL / Aurora** (prod) | delegated to **RDS-managed** backups (PITR + daily snapshots); logical `pg_dump` is an ops step | `aurora_managed` |

The app never claims to back up Postgres itself — it records that RDS owns it and points ops at
`pg_dump` for logical exports.

## Executed drill — SQLite (2026-07-22, reproducible)

```
python - <<'PY'
from app.services.backup import _sqlite_backup, verify_backup
dst, size = _sqlite_backup("legal_server.db")   # consistent online copy
print(verify_backup(dst))                         # restore-verify: open + integrity + core tables
PY
```
**Actual output:**
```
backup file: legalserver-20260722-065559769550.db   size: 1130496 bytes
verify result: {'ok': True, 'integrity': 'ok', 'table_count': 33, 'has_core': True}
```
`verify_backup()` opens the backup as a fresh DB, runs `PRAGMA integrity_check`, and confirms the
core tables exist — i.e. it proves the file is actually **restorable**, not merely present.

Admin-triggered path (same mechanism, audited): `POST /api/admin/backup` (firm admin) → a
`BackupRun` row; history at `GET /api/admin/backups`. Automated nightly at 02:00 via the scheduler
(now durable + idempotent — see Phase 3 / `app/services/scheduler.py`).

## Restore

**SQLite (dev/local):** stop the app; replace `legal_server.db` with the chosen
`legalserver-*.db` backup (verify first with `verify_backup`); restart; hit `/healthz`.

**PostgreSQL / Aurora (prod) — `GATED_OWNER`:**
1. Point-in-time restore or snapshot restore into a **new, clean** cluster (AWS console/CLI — owner).
2. Set `DATABASE_URL` to the restored cluster; run `alembic upgrade head` (no-op if already at head).
3. Run the deploy preflight: `python -m app.ops.release preflight` (must pass — verifies migration
   head + corpus fingerprint + config).
4. Spot-check representative rows: a tenant, an audit entry, a billing subscription, a document, a
   generated draft, an AI conversation (the record types the remaining-gaps prompt calls out).
5. Smoke test: `/healthz`, `/readyz`, login, one grounded research query, one gated draft.

## Corruption / disaster recovery

- **Vector index (Chroma) corruption:** the index is DERIVED — rebuild deterministically from the
  versioned fulltext: `python -c "from app.ai.vector_store import reseed; reseed()"`, then
  `python -m app.ops.release preflight` must show the fingerprint `2965aab084ff` and the expected
  chunk count. No backup of the index is required (this is the Phase 1 property).
- **DB corruption (SQLite):** restore the latest verified backup (above). `reseed()` refuses to run
  below 500 MB free (S0.2) so a disk-full event can't corrupt a rebuild.
- **Aurora failure:** RDS PITR to the last healthy point (owner), then steps above.

## Still owner/infra (not provable from the codebase alone)

- **Encrypted backups to private object storage (S3 SSE-KMS) with lifecycle** — prod uses this
  instead of local disk for durability; `GATED_OWNER` (bucket + IAM + KMS). Tracked in OWNER_QUEUE.
- **A restore drill on prod-like infra** (Aurora + object storage) — the SQLite drill above is
  proven; the prod-infra drill needs the owner's cluster + bucket. Until then this runbook's Postgres
  path is documented, not executed.
- **Nightly CI restore drill** against a localstack/S3 stub — designed (sprint sheet S1.8); wiring
  pending the object-storage decision.
