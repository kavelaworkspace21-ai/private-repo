# Backup & Disaster Recovery

**Sprint:** S4 — Backup & Disaster Recovery Proof · **Written:** 2026-08-04
**Status:** **NO RESTORE HAS EVER BEEN PERFORMED**

> S4's objective is to "turn backup claims into demonstrated recoverability", and its
> acceptance criterion is that *a restore has been performed, not merely configured*. That
> criterion is **not met** and cannot be met by me: it needs AWS access I do not have, against
> a cluster that does not exist.
>
> What follows is everything that can be prepared in advance — the architecture as it actually
> is, RPO/RTO targets awaiting your approval, and a **verification script that has been tested
> in both directions**. The restore itself is yours (B3).

---

## 1. The finding that matters most

**A database backup does not back up the documents.**

> **PARTIALLY ADDRESSED 2026-08-04.** `run_backup()` now archives `data/uploads/` on **both**
> engines, and production **refuses to boot** until the operator declares where files are
> protected. The table below is updated; §1a records exactly what that does and does not buy,
> because the archive alone is not durability.

| Data | Lives in | Covered by an RDS backup? | Recoverable without it? |
|---|---|---|---|
| Matters, clients, users, diary, fees, billing, audit | PostgreSQL | **YES** | no |
| Document **metadata** (filename, `file_path`, case link) | PostgreSQL | **YES** | no |
| Document **bytes** — the actual client files | local disk `data/uploads/<tenant_id>/` | **NO** | **only from the uploads archive** — see §1a |
| Workbench upload bytes + `.pages.json` sidecars | local disk `data/uploads/` | **NO** | **only from the uploads archive** — see §1a |
| Vector index | local disk `chroma_db/` | **NO** | **yes** — derived; rebuild with `reseed()` |
| Legal corpus fulltext | git (`app/legal_corpus/fulltext/`) | n/a | yes — versioned |
| `RELEASE.json`, migrations, source | git | n/a | yes — versioned |
| Source PDFs (~153 MB) | local disk `data/source_pdfs/` | **NO** | yes — re-downloadable, SHA-256 recorded in versioned provenance |

`app/services/storage.py` is **local filesystem only**. Its docstring names S3 as a future
swap ("Phase B can swap in S3 without touching callers") — that swap has not happened. There
is no `boto3`, no bucket, no object storage anywhere in `app/`.

So: restore the database alone and every document row points at a file that is not there.
`read_file()` returns `None`. The UI still lists the document, the matter still shows its
evidence, and the bytes do not exist. **This is silent** — nothing in the database is wrong,
so no database-level check can see it.

### What this means concretely

* **Aurora PITR is not a disaster-recovery plan for this application.** It covers the
  relational half. The half a client would sue over is on an instance disk.
* **If the EC2 instance or container is replaced, uploaded files are gone** unless something
  else is backing up `data/uploads/`. Since 2026-08-04 `run_backup()` archives them (§1a) —
  but to `BACKUP_DIR`, which defaults to the same disk. Durable only once
  `UPLOADS_BACKUP_DIR` points somewhere that survives the instance.
* The asymmetry to keep straight: losing `chroma_db/` is an **outage** (rebuildable from the
  versioned corpus, 15–25 min). Losing `data/uploads/` is **data loss**.

---

## 1a. What was done about it, and what is still yours

**Implemented 2026-08-04** (`app/services/backup.py`, `app/security_gate.py`):

* **`run_backup()` archives the uploads tree on every run, on BOTH engines.** Previously the
  PostgreSQL branch recorded `aurora_managed` and returned, doing nothing — RDS owned the
  relational half and nothing owned the files. The archive is written temp-then-renamed so a
  crash cannot leave a truncated file that looks complete, skips symlinks so it cannot be
  walked out of the tree, preserves the per-tenant directory structure, and shares the
  database backups' rolling retention (`BACKUP_KEEP`, default 7).
* **`verify_uploads_backup()`** reopens an archive and confirms it is readable — the same
  argument as `verify_backup()` for the database. An archive nobody has opened is not known to
  be an archive.
* **The production boot gate now refuses to start** until the operator declares where uploaded
  files are protected, via either `UPLOADS_BACKUP_DIR` (a durable location for the archive) or
  `UPLOADS_DURABLE_STORAGE=1` (an assertion that `data/uploads` is already on backed-up
  storage). Setting `BACKUP_DIR` alone deliberately does **not** satisfy it: it defaults to
  `./backups`, the same disk as the files it would protect, and a default is not a decision.

### What this buys, stated precisely

It converts a **silent** gap into a **loud** one, and makes the files a single artifact to
ship off-box. The app's backup record no longer implies coverage it does not have.

**It is not, by itself, durability.** An archive written to `./backups` sits on the same disk
as the uploads it protects; if the instance dies they die together. The gate is what forces
that to be confronted, but the operator still has to point `UPLOADS_BACKUP_DIR` at storage
that survives the instance.

### Still owner work

1. **Point `UPLOADS_BACKUP_DIR` at durable storage** — a mounted EFS/backup volume, not
   instance disk — **or** set `UPLOADS_DURABLE_STORAGE=1` if `data/uploads` is already on a
   backed-up network mount.
2. **Or complete the S3 swap** `storage.py` was designed for ("behind a small interface so
   Phase B can swap in S3 without touching callers"). That is the architecturally right answer
   and remains undone: it needs a bucket, credentials, and a `boto3` dependency. Not attempted
   here rather than shipped untested — code that handles client files should not be written
   blind against an API it cannot be run against.
3. **Ship the archive off-box**, or the retention is seven copies of the same risk.

---

## 2. Backup architecture as it actually is

`run_backup()` **dispatches on the driver** (`app/services/backup.py`):

### PostgreSQL / Aurora — `status = "aurora_managed"`

For the DATABASE the application performs **no backup of its own** — RDS owns it. It records a
`BackupRun` row saying so:
location *"Amazon RDS automated backups (PITR + daily snapshots)"*. Durability is entirely
RDS's.

That is a defensible design — RDS does this better than an app can — but it means **the
backup only exists if you configured it in AWS.** The app cannot tell whether you did. A green
`aurora_managed` row is a statement of intent, not evidence a backup exists.

**For the FILES this branch now DOES back up** — see §1a. `status` stays `aurora_managed`,
which is correct for the database half, and the uploads archive is recorded in the same row's
`detail` and `size_bytes`. A failure archiving the files fails the whole run: a backup that
silently omits the client's documents is exactly the sort of green result this project keeps
finding and regretting.

### SQLite (dev only) — the app does back up

Online `sqlite3` backup copy into `BACKUP_DIR`, rolling retention of the most recent
`BACKUP_KEEP` files (default **7**). `verify_backup()` reopens a backup file and runs
`PRAGMA integrity_check` plus a core-schema check, so a silently corrupt backup is detectable.


> Note the asymmetry that remains: the **database** half on production is verified by nobody
> but RDS. That is the gap S4 exists to close, and it can only be closed by performing a
> restore.

---

## 3. RPO / RTO — proposed, awaiting owner approval

These are **proposals**, not commitments. They cannot be committed to until a restore has been
timed at least once. Approve, adjust, or reject.

| Target | Proposed | Rationale |
|---|---|---|
| **RPO — relational data** | ≤ 5 minutes | Aurora PITR granularity. Realistic without extra work |
| **RPO — uploaded files** | **currently ∞ (unbounded loss)** | Nothing backs them up. §1 |
| **RTO — restore + verify + serve** | ≤ 4 hours | Snapshot restore, `alembic upgrade head` if needed, index rebuild 15–25 min, verification script, smoke test. Untimed — the first rehearsal sets the real number |
| **Backup retention** | 35 days | AWS PITR maximum; matches a reasonable "noticed it late" window for a legal record |
| **Restore drill cadence** | quarterly | A backup nobody has restored in a year is not a backup |

The RTO is the softest number here. Nothing in it has been measured; the index rebuild is the
only component with an observed duration.

---

## 4. Restore verification — the script

```bash
python scripts/verify_restore.py --database-url "postgresql+psycopg://USER:PASS@restored-host/db?sslmode=require" --files-root /srv/juriscite
```

Exit 0 = every check passed · 1 = a check failed · 2 = usage error.

It connects **directly to the restored database** — deliberately not over HTTP, because a
restore is validated *before* an application is pointed at it.

| Check | What it proves |
|---|---|
| database reachable, schema complete | Every table the models declare exists |
| migration head | Restored schema is at `RELEASE.json`'s revision — an older snapshot lands on an earlier head, and the app then 500s on whichever endpoint touches the newest column |
| tenant_id populated / resolves | No NULLs, no rows pointing at a tenant that was not restored |
| no cross-tenant document leakage | Documents agree with their case's tenant |
| **documents have their files** | **Walks the filesystem.** The §1 gap, made visible |
| document version hashes | Where a sha256 was recorded, the bytes on disk still match — distinguishes *corruption* from *absence* |
| release identity, vector index | Filesystem state: fingerprint and chunk count against `RELEASE.json` |
| write test | Insert + read-back **inside a transaction that always rolls back**, then confirms nothing was left behind |

**Safety:** read-only apart from the write test, which rolls back unconditionally and then
*verifies* the rollback took effect. Safe against a restored production database. The database
URL is never echoed — it holds a password.

### It has been tested in both directions

Against a real database with seeded data, before being committed:

* **DB-only restore → FAIL, exit 1.** Named the missing file: `1/2 sampled document rows point
  at files that DO NOT EXIST (id=2:data/uploads/1/lost.pdf)`.
* **Tampered file → FAIL.** `1 file(s) on disk do not match their recorded sha256 —
  corruption, not just absence`.
* **DB + files restored → PASS, exit 0**, 15 checks.

One defect it caught in itself on first run: `document_versions` spells the column
`storage_path`, while `documents` uses `file_path`. Assuming they matched made the hash check
**skip silently** — the exact shape of a check that reports nothing. It now fails loudly if it
cannot read the table.

---

## 5. Post-restore validation — the full sequence

Run in this order. Do not skip ahead; each step assumes the previous passed.

1. **Verify the restored database, before any application touches it:**

   ```bash
   python scripts/verify_restore.py --database-url "$RESTORED_URL" --files-root /srv/juriscite
   ```

2. **Bring the schema to head if the snapshot predates the release:**

   ```bash
   alembic upgrade head
   ```

3. **Rebuild the vector index if this host has none** (it is derived and gitignored; expect
   15–25 min of CPU embedding):

   ```bash
   python -c "from app.ai.vector_store import reseed; reseed(force=True)"
   ```

4. **Preflight — the build must be the audited release:**

   ```bash
   python -m app.ops.release preflight
   ```

5. **Start the application** and confirm it boots. The boot gates raise rather than log, so a
   running process has already passed them.

6. **Smoke-test the restored deployment end to end:**

   ```bash
   python scripts/smoke_test.py https://RESTORED_HOST --admin-token "$ADMIN_TOKEN"
   ```

7. **Confirm by hand, because no script should be trusted alone here:**
   * a known matter opens and shows its documents;
   * **a document actually downloads** — this is the §1 gap, and it is the one thing a
     database-only restore will silently get wrong;
   * a login works for an account you already control.

8. **Record the wall-clock time from restore start to step 7 passing.** That number is the
   real RTO; §3's is a guess until it exists.

---

## 6. What is explicitly NOT covered

Stated so the scope is not overestimated later:

* **Uploaded client files.** §1. The single largest gap in this document.
* **Any restore at all.** Nothing here has been executed against AWS.
* **Cross-region / cross-account recovery.** Not designed, not configured.
* **Backup encryption and key custody.** RDS defaults apply; not reviewed.
* **Deletion-and-restore interaction with DPDP erasure.** If a user exercises erasure and you
  later restore a snapshot predating it, **their data comes back**. There is no re-erasure
  step in this procedure. That is a compliance issue as much as a technical one, and it needs
  a decision before real client data exists — likely: log erasures durably outside the
  database and replay them after any restore.
* **Alerting on backup failure.** There is no error tracker; a failed backup would be silent.
  H3 / OWNER-12.

---

## 7. Owner actions to close S4

| # | Action |
|---|---|
| 1 | Enable Aurora automated backups; set retention (proposed 35 days) |
| 2 | **Decide the `data/uploads/` question** (§1) — durable storage, file backup, or documented acceptance |
| 3 | Approve or adjust the RPO/RTO targets (§3) |
| 4 | **Perform a real restore into a scratch cluster** |
| 5 | Run §5 against it and record the wall-clock RTO |
| 6 | Decide the erasure-vs-restore policy (§6) |

Until #4 happens, the honest status of backups on this system is: *configured in intent,
unproven in fact.*
