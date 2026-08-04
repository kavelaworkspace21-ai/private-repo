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

| Data | Lives in | Covered by an RDS backup? | Recoverable without it? |
|---|---|---|---|
| Matters, clients, users, diary, fees, billing, audit | PostgreSQL | **YES** | no |
| Document **metadata** (filename, `file_path`, case link) | PostgreSQL | **YES** | no |
| Document **bytes** — the actual client files | local disk `data/uploads/<tenant_id>/` | **NO** | **NO — gone forever** |
| Workbench upload bytes + `.pages.json` sidecars | local disk `data/uploads/` | **NO** | **NO — gone forever** |
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
  else is backing up `data/uploads/`. Nothing currently is.
* The asymmetry to keep straight: losing `chroma_db/` is an **outage** (rebuildable from the
  versioned corpus, 15–25 min). Losing `data/uploads/` is **data loss**.

**Owner decision required.** Either:
1. put `data/uploads/` on durable storage (EFS with backup, or complete the S3 swap the code
   was designed for), **or**
2. add a file-level backup of `data/uploads/` to the same schedule and retention as the
   database, **or**
3. accept and *document in-product* that uploaded files are not disaster-recoverable.

Option 3 is not really available before G6/G7 with real client data.

---

## 2. Backup architecture as it actually is

`run_backup()` **dispatches on the driver** (`app/services/backup.py`):

### PostgreSQL / Aurora — `status = "aurora_managed"`

The application performs **no backup of its own**. It records a `BackupRun` row saying so:
location *"Amazon RDS automated backups (PITR + daily snapshots)"*. Durability is entirely
RDS's.

That is a defensible design — RDS does this better than an app can — but it means **the
backup only exists if you configured it in AWS.** The app cannot tell whether you did. A green
`aurora_managed` row is a statement of intent, not evidence a backup exists.

### SQLite (dev only) — the app does back up

Online `sqlite3` backup copy into `BACKUP_DIR`, rolling retention of the most recent
`BACKUP_KEEP` files (default **7**). `verify_backup()` reopens a backup file and runs
`PRAGMA integrity_check` plus a core-schema check, so a silently corrupt backup is detectable.

> Note the asymmetry: the **dev** path has a verification function, and the **production**
> path has none, because RDS owns it. That is the gap S4 exists to close, and it can only be
> closed by performing a restore.

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
