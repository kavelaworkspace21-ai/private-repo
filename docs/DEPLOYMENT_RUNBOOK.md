# Deployment Runbook

**Scope:** deploying a Juriscite release candidate to the EC2 app box (in-VPC to Aurora).
Grounded in `deploy/deploy_ec2.sh`, `RELEASE.json`, and `app/ops/release.py`. Owner-only
infrastructure steps are marked `GATED_OWNER`.

## Release identity (what a deploy must land)

`RELEASE.json` pins it: app `0.2.0` · corpus fingerprint `2965aab084ff` · migration head
`81665ba86789` · 8,646 chunks · collection `indian_law_sections` · embedding `onnx-default-minilm`.
The deploy **fails closed** if the running state doesn't match (see preflight below).

## The artifact is reproducible (no local-disk dependency)

The Chroma index is DERIVED from the versioned `app/legal_corpus/fulltext/*.json`. A clean box
does NOT need a copied index — it regenerates one and proves it by fingerprint:

```bash
python -m alembic upgrade head
python -c "from app.ai.vector_store import reseed; reseed()"      # deterministic rebuild
python -m app.ops.release preflight                               # must pass (fingerprint + count + head + secrets)
```

## Deploy steps (`deploy/deploy_ec2.sh`, run as `ubuntu` ON the box)

1. Sanity (zip present, venv present).
2. Back up current CODE for rollback (`juriscite_codebak_<stamp>.tgz`; excludes venv/db/chroma).
3–4. Unzip + `rsync` code in (NO `--delete`; preserves venv/.env/chroma/db).
5. `pip install -r requirements.txt` (no-op if unchanged).
6. `alembic upgrade head` (expected head read from `RELEASE.json`, no longer hardcoded).
7. **Release preflight — fail-closed.** `python -m app.ops.release preflight` aborts the deploy on
   a stale/altered corpus, an unbuilt/mismatched index, migration drift, or missing
   `JWT_SECRET`/`FIELD_ENCRYPTION_KEY`. If it flags ONLY the index count → `reseed()` then re-run.
8. Restart the `legalserver` systemd unit + smoke `/healthz` (liveness) and `/readyz` (index ready).

**Success looks like:** service active · `alembic current` == the RELEASE.json head ·
`/healthz` → `{"soul":"intact","db":"ok"}` · `/readyz` → `{"status":"ready"}`.

## Rollback

- **Code:** extract `juriscite_codebak_<stamp>.tgz` back into the app dir, restart.
- **Migrations:** `alembic downgrade -1` per step, or restore the RDS snapshot (owner).
- **Index:** `reseed()` rebuilds it from fulltext; preflight verifies the fingerprint.
- Confirm rollback with `/healthz` + `/readyz` + `python -m app.ops.release status`.

## Observability during/after deploy

- `python -m app.ops.release status` → JSON identity (version, migration head, fingerprint, index
  count, model name, config-presence booleans; NO secrets). Also exposed at admin `GET /api/admin/status`.
- `/healthz` (liveness) and `/readyz` (readiness) return 503 when unhealthy/not-ready so a load
  balancer pulls a bad instance.
- Scheduled-job health: `app/services/scheduler.job_health()` / `stale_jobs()` (missed reminders/
  backups/drift). Alert-channel wiring is `GATED_OWNER` (OWNER-12).

## GATED_OWNER (not provable from the codebase; must exist before a real prod deploy)

- **Aurora cluster** started + in-VPC; `DATABASE_URL` set in the box's `.env` (secret store, not repo).
- **`FIELD_ENCRYPTION_KEY`** set in prod (preflight blocks deploy without it — this dev `.env` lacks it).
- Trusted **HTTPS + DNS**, restricted **security groups**, least-privilege **IAM**, **KMS**/secret manager.
- Durable **encrypted object storage** (S3 SSE-KMS) for uploads/backups instead of local EC2 disk.
- A **staging** environment to run this whole runbook end-to-end before production.

None of the above is signed off; do NOT call a deploy production-ready while they or the human gates
(G1/G6/G7/G8) remain open. See `docs/GAP_MATRIX.md` + `docs/OWNER_QUEUE.md`.
