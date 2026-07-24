# Release Manifest & Reproducible Build (Phase 1)

**Purpose:** make a Juriscite release a *reproducible, verifiable artifact* instead of a
copy of local Windows `D:`-drive state. Closes the P0 "deploy depends on packaging Chroma
from a local drive" gap.

## The key fact

The Chroma vector index is **derived**, not source. Its inputs are the version-controlled
source-verified fulltext files in `app/legal_corpus/fulltext/*.json`. Therefore a clean
machine can **regenerate the index deterministically** and prove it matches the shipped
release by fingerprint — no local index snapshot is required.

## Release identity — `RELEASE.json`

Pinned at the repo root; the single source of truth for what a verified release *is*:

| Field | Meaning |
|---|---|
| `app_version` | from `app/version.py` (single source) |
| `corpus_fingerprint` | 12-hex over every act's source SHA + parsed content (`corpus_updates.corpus_version()`) |
| `migration_head` | expected Alembic head revision |
| `expected_chunk_count` | embedded chunks after a clean reseed |
| `embedding_model` | `onnx-default-minilm` (or `openai:text-embedding-3-small` if `OPENAI_EMBEDDINGS_KEY` set) |
| `chroma_collection` | `indian_law_sections` |
| `commit` | git commit the release was frozen from (Phase 0) — the audited source revision |

**Current release:** `0.2.0` · fingerprint `2965aab084ff` · migration head `81665ba86789` ·
8,646 chunks · 50 verified acts · commit `af1774d`.

## Source identity (Phase 0)

Before 2026-07-24 the project had **no version control**, so a "verified release" could not be
pinned to a revision — the corpus and migrations were verifiable but the *code* was not.
Baseline commit `1b7e99b` records the audited state; `RELEASE.json.commit` pins the release
source. `live_status()` (and therefore `/api/admin/status`) reports `commit`, `branch` and
`tree_dirty`.

Two consequences for deploys:

- A **dirty working tree** fails preflight — you cannot deploy uncommitted changes as an
  audited release.
- A tree whose commit ≠ the pinned commit fails preflight, with exactly one exception:
  commits differing **only** in `RELEASE.json`. `freeze()` stamps the current HEAD into
  `RELEASE.json`, so committing that stamp necessarily advances HEAD by one; without the
  exception the pin could never be satisfied. Any other changed file fails the match.

Both checks degrade to no-ops when git is unavailable (a production tarball deploy has no
`.git`), where the pinned corpus/migration/version fields carry the guarantee instead.
`git status` failing yields `None`, never `False` — unknown is not treated as clean.

Regenerate after any corpus/migration change: `python -m app.ops.release freeze`
(the test `test_release_ops.py::test_release_json_matches_actual_corpus_and_migrations`
fails if RELEASE.json drifts from the repo, so it can't go stale silently).

## Build a release on a clean machine

```bash
python -m venv venv && venv/Scripts/python -m pip install -r requirements.txt   # (venvs are NOT portable — always rebuild)
python -m alembic upgrade head                                                  # schema
python -c "from app.ai import vector_store as vs; vs.reseed()"                  # regenerate index from versioned fulltext
python -m app.ops.release preflight --no-require-secrets                        # verify identity (dev)
```

The reseed is deterministic; if the rebuilt index's fingerprint or chunk count doesn't match
`RELEASE.json`, **preflight fails and the deploy must stop**. No `D:`-drive snapshot, no
undocumented local state.

## Preflight — fail-closed deploy gate

`python -m app.ops.release preflight` exits **non-zero** (deployment must not proceed) when any of:

- corpus fingerprint ≠ `RELEASE.json` (stale or altered corpus),
- vector index count ≠ `expected_chunk_count` (index not built / partial reseed),
- migration head ≠ `RELEASE.json` (run `alembic upgrade head`),
- app version ≠ `RELEASE.json`,
- missing `JWT_SECRET` / `FIELD_ENCRYPTION_KEY` (unless `--no-require-secrets` for dev),
- free disk < 500 MB on the index volume,
- **uncommitted working-tree changes** (unless `--allow-dirty` for local checks),
- **commit ≠ the pinned release commit** — this tree is not the audited release.

Deploy scripts should call `preflight` (prod mode, secrets required) and abort on non-zero.
This is consistent with the app's fail-closed philosophy: a bad release refuses to serve.

## Operational status — `python -m app.ops.release status`

Emits JSON of the live identity (version, fingerprint, migration head, chunk count, embedding
model, python, disk, and config **presence booleans** — never secret values). Safe for an
ops/status endpoint. Boot-free: it does not import `app.main`, so it never trips the soul/
prohibited boot gates and can run during recovery.

## Still owner/infra work (not covered here)

Trusted HTTPS/DNS, restricted networking, least-privilege IAM, KMS/secret-manager, durable
encrypted object storage, and the Aurora cluster remain `GATED_OWNER` (see `docs/GAP_MATRIX.md`,
`docs/OWNER_QUEUE.md`). This manifest makes the *artifact* reproducible; the *infrastructure*
it deploys onto is a separate, owner-gated track (Phase 2).
