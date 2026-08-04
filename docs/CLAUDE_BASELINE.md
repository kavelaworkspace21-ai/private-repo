# Juriscite — S0 Baseline

**Captured:** 2026-08-04 · **Commit:** `caba687` · **Branch:** `main` · **Commit count:** 97
**Machine-readable companion:** [`artifacts/baseline/`](../artifacts/baseline/)

The reference point every later sprint diffs against. Facts here were produced by running the
commands, not by reading the code and inferring.

> **Deviation from the sprint order, stated plainly.** S0 is specified as a *pre-change*
> baseline whose acceptance criterion is "no source code behaviour is changed". This baseline
> was captured **after** S1, at `caba687`, because S1 was already in flight when the roadmap
> was ingested. It is therefore a baseline of the **post-S1** tree, not the pre-S1 one. The
> practical consequence is small — S2 onward compare against this, and the S1 changes are
> individually recorded in [`CI_RELEASE_EVIDENCE.md`](CI_RELEASE_EVIDENCE.md) — but it should
> not be read as "the state before any of this work".

---

## 1. Environment

| | |
|---|---|
| Python (local) | 3.14.6 · Windows-11-10.0.28020-SP0 |
| Python (CI) | 3.12 · ubuntu-latest |
| Dependencies | `requirements.lock`, **154 pinned = 154 installed** |
| Lock SHA-256 | `cf364f5b4a1b489c94c8625f34f7c86bd9f00c5d4bce8191c2c94c18e1a719c0` |

`requirements.txt` is the **intent** file and is 23/24 unpinned (`>=` ranges). Everything —
local, CI, deploy — installs from the **lock**.

## 2. Check results at baseline

| Check | Command | Result | Artifact |
|---|---|---|---|
| Test suite (SQLite) | `pytest tests/ -q` | **785 passed, 0 failed** | `junit-sqlite.xml` |
| Test suite (Postgres) | CI only | **785 passed** (run #15) | CI artifact `junit-postgres` |
| Lint | `ruff check .` | **0 findings** (`DTZ` + `F`) | `ruff.json` |
| Migration integrity | `pytest tests/test_migrations.py -q` | pass | — |
| Dependency audit | `pip-audit -r requirements.lock` | **clean**, 2 documented waivers | `pip-audit.json` |
| Installed packages | `pip freeze` | 154 | `pip-freeze.txt` |

Waivers (`security/pip-audit-waivers.txt`): `ecdsa` — unused, JWTs are HS256; `chromadb` —
ingests only our own verified corpus. Both are vulnerabilities with **no upstream fix**; where
a fix exists the pin is bumped instead (as with `aiohttp` and `cryptography` in S1).

## 3. Release identity

```json
{ "app_version": "0.2.0", "corpus_fingerprint": "a1fecc33d3e0",
  "migration_head": "e2b7c9d40a15", "chroma_collection": "indian_law_sections",
  "embedding_model": "onnx-default-minilm", "expected_chunk_count": 8914,
  "verified_acts": 50, "generated_at": "2026-07-31", "commit": "6929ccf" }
```

`python -m app.ops.release preflight` fails closed on any drift and exit-1s a deploy. It has
caught real drift twice.

## 4. CI

| | |
|---|---|
| Workflow | `.github/workflows/ci.yml` |
| Jobs | `test` (SQLite) · `test-postgres` (real `postgres:16`) · `audit` — **all blocking** |
| Green baseline | [run #15](https://github.com/kavelaworkspace21-ai/private-repo/actions/runs/30885314546) at `e4a6ee6` |
| Evidence | [`CI_RELEASE_EVIDENCE.md`](CI_RELEASE_EVIDENCE.md) |

Timings: `test` 5.4 min · `test-postgres` 5.1 min · `audit` 0.4 min.

## 5. Architecture reconnaissance

### Database configuration paths

| Path | Role |
|---|---|
| `app/db/config.py` | The **only** place `DATABASE_URL` is read for the engine; defaults to `sqlite:///./legal_server.db` |
| `app/db/session.py` | `get_db()` generator — the single dependency-injected session source |
| `app/security_gate.py:80` | Refuses production boot when `DATABASE_URL` is unset, instead of silently using local SQLite |
| `app/ops/release.py:116` | Records **presence only** (`bool`), never the value |

### LLM egress points

All model calls originate in: `app/ai/agent.py`, `app/ai/case_law.py`, `app/ai/llm_config.py`,
`app/routers/ai_chat.py`, `app/routers/ai_drafting.py`, `app/routers/library.py`,
`app/services/workbench/engine.py`, `app/services/workbench/uploads.py`.

**Every one is behind `require_ai_consent`** (`app/auth/dependencies.py:87`), which delegates
to `has_current_consent` in `app/services/privacy.py`. There is deliberately **no environment
flag to switch it off** — "consent enforcement, but disabled in production" is not consent.
Refusal is a 403 that names the remedy (`/consent`).

Outputs pass `validate_answer()`, which **removes** sentences carrying unverifiable citations
and withholds the answer entirely if too little survives. It withholds; it does not warn.

### Tenant-scoped access

`app/services/tenancy.py` is the chokepoint: `current_tenant_id`, `get_owned_case`,
`get_owned_client`, `scoped_children`, `get_owned_child`, `write_audit`. A cross-tenant IDOR
sweep is in the suite.

### Boot gates

`assert_secrets_sane()` (`app/security_gate.py:115`), `assert_prohibited_disabled()`
(`app/legal_config.py:44`), `assert_soul_intact()`, `_disk_preflight()` (`app/main.py`).
Unset `ENVIRONMENT` is treated as **production**, so forgetting it fails closed.

### Corpus commands

`python -m app.ai.ingest_statutes --list | <act_id> | all`, and
`reseed()` in `app/ai/vector_store.py` (HTTP: `POST /api/admin/reseed-corpus`,
`POST /api/admin/ingest-statutes`, both firm-admin). Full detail and the crash-safety
guarantees are in [`ENGINEERING_RUNBOOK.md`](ENGINEERING_RUNBOOK.md).

## 6. Corpus state

50 acts · 8,710 sections and schedule entries · 8,914 index chunks · fingerprint
`a1fecc33d3e0`.

Known-wrong and **recorded, not fixed**: Stamp ss.8B/8E/8F/23A unaddressable by number;
`it_act_2000` and `legal_services_1987` recoveries would destroy Definitions text; Mediation
ss.49/55 absent; Constitution Schedules 1–6/8/9/11/12 not ingested; IPC 354E duplicate section
number. Full list in [`CORPUS_LIMITATIONS.md`](CORPUS_LIMITATIONS.md) and §2 of
[`FINAL_AUDIT_2026-07-31.md`](FINAL_AUDIT_2026-07-31.md).

`tests/test_corpus_contamination.py` asks the question none of the older integrity checks did:
**is the text actually law**, rather than merely present. Counts, coverage, fingerprints and
the citation gate all only ever asked whether a section existed — a corpus can be complete,
reproducible, fingerprinted and fully covered while a section quietly contains the *amending*
Act instead of the provision. Ten sections across three acts were in exactly that state, nine
of them since before version control.

## 7. Reproducing this baseline

```bash
pytest tests/ -q --junitxml=artifacts/baseline/junit-sqlite.xml
ruff check . --output-format json > artifacts/baseline/ruff.json
pip freeze > artifacts/baseline/pip-freeze.txt
pip-audit -r requirements.lock $(grep -vE '^\s*#|^\s*$' security/pip-audit-waivers.txt | awk '{print "--ignore-vuln " $1}') -f json > artifacts/baseline/pip-audit.json
python -m app.ops.release status
```

`artifacts/` is gitignored except `artifacts/baseline/`, which is versioned deliberately — a
baseline nobody can diff against is not a baseline.

**What cannot be reproduced locally:** the PostgreSQL suite. There is no Docker and no local
Postgres server on this box, so CI's `test-postgres` job is the only place it runs. Its JUnit
XML artifact is the only evidence that exists, which is why it uploads with `if: always()`.

## 8. Caveats on trusting this document

Two lessons this project paid for, worth carrying into every later sprint:

1. **A claim about the corpus is a claim to verify, not inherit.** This project has been wrong
   in both directions — believing text was present when it was amending legislation, and
   believing text was missing (Order XV-A) when it had been there all along.
2. **Ask of any check: what would make this fail, and has it ever?** Nearly every defect found
   in the last week was a check that reported nothing — a probe that raised instead of
   asserting, a suite whose exit code was swallowed by `tail`, a status check matching a
   sentinel echoed from elsewhere, an assertion written `assert x not in y or True`, a CI gate
   configured `continue-on-error`, and a test that passed *because* the corpus was corrupt.

S1's negative control (run #13) exists because of lesson 2.
