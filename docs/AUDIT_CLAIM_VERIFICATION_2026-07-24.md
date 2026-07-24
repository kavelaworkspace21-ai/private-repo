# Audit Claim Verification — 22 July report re-adjudicated

**Date:** 2026-07-24 · **Adjudicated against:** `docs/FINAL_AUDIT_REPORT_2026-07-22.md`
**Baseline commit:** `1b7e99b` (first version-controlled commit) · **Release commit:** `af1774d`

Required by the vision-alignment prompt: mark every 22 July claim `CONFIRMED`,
`CONTRADICTED`, or `NOT_YET_PROVEN`, with evidence. Verdicts below come from re-running the
checks on 24 July, not from re-reading the report. Where the 22 July report was wrong, it is
marked wrong; where an external criticism of it was wrong, that is marked too.

---

## CONFIRMED

| # | Claim | Evidence (2026-07-24) |
|---|---|---|
| 1 | Version 0.2.0; migration head `81665ba86789` (14 migrations) | `app.ops.release freeze` recomputed both from the Alembic script directory |
| 2 | Corpus fingerprint `2965aab084ff`, 8,646 chunks, 50 acts | `freeze()` **recomputed** the fingerprint (hashes parsed content, not just source SHAs) and counted the live Chroma collection — identical |
| 3 | Release preflight PASSING in prod mode | `python -m app.ops.release preflight` → exit 0, run from the committed tree with secrets required |
| 4 | Scale: 22 routers · 151 endpoints · 26 models · 71 test files · 18 page templates | Re-counted from the filesystem; every number matched exactly |
| 5 | **Consent is NOT enforced at the AI boundary** (report listed this as an open ⛔ gap) | `ConsentRecord` appears only in `account.py` (export/delete) and `auth.py` (record/read). `ai_chat.py`, `ai_drafting.py`, `workbench.py` depend on `require_ai_access` — a *verification* gate, flag-gated off in beta. The report was honest about its own gap |
| 6 | Cross-tenant isolation covers cases, clients, documents+download, hearings, drafts, fees, diary | Two files, not one: `test_idor_sweep.py` (cases/clients/documents incl. download, versions, delete) + `test_tenant_rbac_deep.py::test_cross_tenant_isolation_all_objects` (hearings, drafts, fees, diary tasks; read/update/delete + create-on-foreign-case). I doubted this claim and checked; it holds |
| 7 | Kanoon is the only genuinely billed service, and its results are never model grounding | `case_law.py` is the sole caller; results render as links in UI only, never enter prompt assembly |
| 8 | Upload hardening: extension allowlist + 20 MB cap + magic-byte sniffing + tenant-separated storage | `app/services/storage.py` `_MAGIC` map + `_content_matches_ext()` in `validate()` |
| 9 | Scheduler durability: exactly-once per slot via `UNIQUE(job_id, slot_key)` | `app/services/scheduler.py` `run_tracked_job()`; migration `81665ba86789` |
| 10 | No version control existed | `git init` on 24 July found no repo, no parent repo, no nested repos. Now remediated |
| 11 | Test suite 580 passed / 0 failed, 2 third-party warnings | Re-run from the committed baseline: **585 passed / 0 failed** in 14m42s (580 + 5 new release-identity tests). Same 2 third-party warnings (starlette/httpx, chromadb) |

---

## CONTRADICTED

### C1 — "Citation **hard-gate**" — it is a flag, not a gate

The vision prompt's criticism is **correct and I am upholding it against my own report**.

`app/ai/safety.py:189` — the function's own docstring calls itself a `Hard-gate`, but:

```python
notice = ("\n\n---\n⚠ " + CITATION_GATE_NOTICE + ...)
return answer.rstrip() + notice, bad
```

It **appends a warning and returns the answer**. An answer citing a provision absent from the
retrieved sources is still delivered to the advocate. The Phase 4 `citation_guard.integrity_event()`
added on 22 July is explicitly additive and non-blocking. Nothing in the path withholds, repairs,
or refuses.

*In fairness to the report:* PART 3's parenthetical — "any citation not in the retrieved sources is
**flagged** to the advocate" — describes the behaviour accurately. The failure is the label
"hard-gate" in both PART 3 and PART 5, which claims an enforcement strength the code does not have.
For a legal tool that distinction is the whole point, so this is graded CONTRADICTED, not cosmetic.

**Status:** Phase 2 work. Repair-or-withhold, not warn.

### C2 — "Browser-verified" ✅ marks extend beyond what was actually browsed

PART 1 states browser verification for **six** pages (dashboard, assistant, cases, library,
drafting, workbench) and then awards `✅ VERIFIED` to **thirteen**. Sign In, Register, 2FA Setup,
Court Diary, Drafts, Firm, Notifications carry a ✅ that no browser evidence in that session
supports. They are exercised by tests, which is real evidence — but it is not the browser
verification the ✅ implies.

**Status:** Phase 7 work (all 18 pages, browser + a11y + visual + PWA).

---

## NOT_YET_PROVEN

| # | Claim | Why it is not proven |
|---|---|---|
| N1 | "PostgreSQL/Aurora ready" (implied by the deployment posture) | The CI Postgres lane's suite step is still `continue-on-error: true` and has never run green. `alembic upgrade head` on PG is blocking, the **suite** is not. Phase 3 makes it blocking |
| N2 | Backups: "drill executed" | True for SQLite online-copy + verify. Postgres restore delegates to RDS-managed and has never been exercised — there is no Aurora cluster |
| N3 | DPDP export/deletion completeness | `account.py` deletes DB rows. Propagation to uploaded files, the vector index, backups and logs is unverified. Report said so; still unverified |
| N4 | Timeline estimates (6–9 wks beta, 10–14 wks production, 4–5 mths paid launch) | Engineering-informed estimates dependent on external parties (counsel, pentest, KYC, advocate recruitment). Unfalsifiable now; the report's own caveat stands |
| N5 | "Injected instructions are contained as data (deterministically tested)" | Tests are deterministic string-level checks, not adversarial evaluation against a live model. Real prompt-injection resistance needs the Phase 3 eval suite |

---

## The five highest-risk remaining gaps

Ranked by *harm if it fires*, not by effort.

1. **Fabricated citations reach the advocate with only a warning.** (C1) A hallucinated section in
   a filing is the single worst failure this product can have, and today the system's response is a
   notice appended below the answer, which a hurried advocate will scroll past. Streaming makes it
   worse: tokens are presented as final before any check runs.

2. **Consent is not enforced at the AI boundary.** Client matter text can reach a third-party LLM
   with no recorded consent check. This is a DPDP exposure and a G6 blocker, and it is one
   dependency away from being fixed.

3. **A live paid Kanoon key fires automatically on every dashboard load.** `index.html`'s
   `latestFromCourts()` calls `/api/research/latest-judgments` unconditionally for every user on
   every visit. There is no `KANOON_ENABLED` flag — enablement is inferred purely from the key
   being present. Uncapped per-use billing on the highest-traffic page.

4. **No proof the app runs correctly on PostgreSQL.** Every one of the 580 tests that has ever
   passed, passed on SQLite. Production is Aurora. Silent behavioural differences (case
   sensitivity, transaction semantics, type coercion) would surface first in production.

5. **Deletion and export do not verifiably propagate.** A DPDP erasure request today clears DB rows
   while leaving uploads, vector-index entries, backups and logs. The right exists in the UI; the
   guarantee behind it does not.

---

## Note for the owner — credential hygiene

`INDIAN_KANOON_API_KEY` in the local `.env` is a **live paid key**. It is correctly gitignored and
was **not** committed (verified before the baseline commit). However, it was displayed in plaintext
in the 24 July working session while tracing the Kanoon call path — my error; I should have matched
on the variable name only. Treat it as exposed-to-transcript and **rotate it at Indian Kanoon**.
Rotation is owner-only. Nothing else was exposed: `.env`, `*.pem`, tokens, local databases and
`data/uploads/` are all excluded from version control and verified absent from the commit.

---

*Adjudicated 2026-07-24 against the committed baseline. Where this document and the 22 July report
disagree, this document governs.*
