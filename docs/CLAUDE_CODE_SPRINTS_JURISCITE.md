# Juriscite — Claude Code Execution Sprints
## Post-Audit Roadmap to Release

**Baseline:** `FINAL_AUDIT_2026-07-31.md`  
**Audited HEAD:** `0c1aca3`  
**App version:** `0.2.0`  
**Corpus fingerprint:** `a1fecc33d3e0`  
**Baseline tests:** 782 passed / 0 failed locally on SQLite  
**Corpus:** 50 acts, 8,710 sections + schedule entries  
**Vector index:** 8,914 chunks  
**Commits:** 88

---

## 0. Purpose

This document is the execution plan for **Claude Code** to take Juriscite from the audited
pre-release state to a controlled production release.

The goal is **not** to blindly implement every possible feature. The goal is to:

1. close the release-blocking engineering gaps;
2. prove the application against PostgreSQL/Aurora;
3. harden CI/CD and deployment safety;
4. improve corpus integrity without silently changing legal content;
5. add operational observability and resilience;
6. prepare explicit human/legal/security gates;
7. keep governance constraints intact.

Claude Code should behave as an **engineering agent**, not as a legal decision-maker.

---

# 1. Non-Negotiable Project Rules

Claude Code MUST preserve these rules unless the owner explicitly changes them.

### Legal-data rules

- Never invent, paraphrase, or "repair" statutory text as though it were law.
- Never silently resolve ambiguous corpus evidence.
- Preserve source provenance for every legal-data change.
- Any uncertain legal-content change must be marked `PENDING_LEGAL_REVIEW`.
- Official-source material remains the grounding authority.
- Indian Kanoon may be used as a retrieval/reference integration, but **must not become
  model grounding by default**.
- Keep `KANOON_ENABLED=false` unless explicitly authorized.
- Judgment-corpus ingestion is **deferred by governance**.
- Do not build prediction, person-scoring, judge-profiling, or eCourts scraping.

### Safety rules

- Preserve fail-closed boot gates.
- Preserve citation withholding behavior.
- Preserve consent enforcement at every LLM egress point.
- Preserve tenant isolation.
- Never weaken a test merely to make CI green.
- Never delete a failing test without proving that the requirement itself changed.
- Never disable security checks to unblock deployment.

### Release rules

- Do not deploy from an un-audited or drifting tree.
- Preserve `RELEASE.json` and release identity checks.
- Every migration must be tested against PostgreSQL.
- Every production backup claim must be backed by an actual restore test.
- Do not enable live billing until the owner completes the required human gates.

---

# 2. How Claude Code Should Work

Claude Code should use its capabilities aggressively:

- inspect the whole repository before changing architecture;
- search code globally before modifying behavior;
- inspect git history and blame when a behavior is unclear;
- run focused tests first;
- run the complete relevant suite after each sprint;
- create small, reviewable commits;
- use parallel investigation where independent workstreams exist;
- use subagents for independent audits/research inside the repository;
- compare SQLite and PostgreSQL behavior rather than assuming equivalence;
- inspect CI configuration and actual CI failures;
- generate scripts/tests that reproduce every production bug found;
- use static analysis and repository-wide searches;
- update documentation as part of the implementation;
- leave an evidence trail in commit messages and audit artifacts.

### Claude Code operating loop

For every sprint:

1. **READ** — inspect the relevant code, tests, docs, CI, and history.
2. **PLAN** — write a short implementation plan before editing.
3. **REPRODUCE** — reproduce the current failure or establish a baseline.
4. **IMPLEMENT** — make the smallest safe change.
5. **TEST** — focused tests first, then broader regression tests.
6. **ADVERSARIAL CHECK** — try to make the new control fail.
7. **AUDIT** — inspect the diff, migration, security implications, and release impact.
8. **COMMIT** — one coherent commit or a small logical commit series.
9. **REPORT** — record what changed, tests run, remaining uncertainty, and evidence.

Claude Code should stop and request owner input when a decision is explicitly marked
`OWNER`, `LEGAL`, `SECURITY`, `AWS`, or `BILLING`.

---

# 3. Sprint Map

| Sprint | Objective | Priority | Owner dependency |
|---|---|---:|---|
| S0 | Baseline and repository reconnaissance | P0 | None |
| S1 | Make CI genuinely green | P0 | None |
| S2 | PostgreSQL production-readiness | P0 | None |
| S3 | Aurora deployment rehearsal | P0 | AWS owner |
| S4 | Backup + disaster recovery proof | P0 | AWS owner |
| S5 | Security/privacy release hardening | P0 | Human review |
| S6 | Corpus integrity hardening | P1 | Legal review where flagged |
| S7 | Parser recovery work | P1 | Legal review where ambiguous |
| S8 | Performance, rate limiting, observability | P1 | Owner choices |
| S9 | Release engineering + canary deployment | P0 | AWS owner |
| S10 | Human/legal release gate package | P0 | Owner + lawyer |
| S11 | Final adversarial release audit | P0 | Owner |
| S12 | Production launch | GO/NO-GO | Owner |

---

# S0 — Baseline Lock & Reconnaissance

## Objective

Create a machine-verifiable baseline before further changes.

## Tasks

- Verify current git HEAD and working-tree cleanliness.
- Record Python/runtime versions and dependency lock state.
- Run the complete SQLite suite.
- Run lint/type/static checks currently configured.
- Inspect CI workflow files.
- Identify all database configuration paths.
- Identify all LLM egress points and confirm consent gates.
- Identify all tenant-scoped database access paths.
- Identify deployment/preflight scripts.
- Identify corpus ingestion/reseed/index-build commands.
- Map all existing release gates.
- Review recent git history around the audit fixes.

## Claude Code deliverables

Create:

- `docs/CLAUDE_BASELINE.md`
- `docs/ENGINEERING_RUNBOOK.md`
- `artifacts/baseline/` containing machine-readable test/check outputs where appropriate.

## Acceptance criteria

- Baseline is reproducible.
- No source code behavior is changed.
- Every subsequent sprint can compare against this baseline.

---

# S1 — CI GREEN, FOR REAL

## Objective

Get CI to a genuinely green state without weakening gates.

## Tasks

- Inspect every current CI job and its failure output.
- Fix remaining CI failures.
- Ensure dependencies come from the locked requirements.
- Ensure checkout depth supports release-history checks.
- Ensure SQLite tests run with correct exit-code propagation.
- Ensure PostgreSQL tests run without pathological per-test schema creation.
- Preserve migration integrity checks.
- Run both SQLite and PostgreSQL suites in CI.
- Add explicit failure diagnostics to CI.
- Add a final machine-readable test summary.
- Add repository-wide linting.
- Add pre-commit or equivalent repo-wide lint enforcement.

## Critical rule

Do not use `|| true`, swallowed exit codes, relaxed assertions, skipped tests, or reduced
coverage to obtain green CI.

## Acceptance criteria

- CI is green on a clean commit.
- SQLite suite passes.
- PostgreSQL suite passes.
- Migration checks pass.
- Lint passes.
- Release identity checks pass.
- At least one deliberately broken test proves the CI lane actually fails when it should.

## Evidence

Record CI run URL/ID and commit SHA in `docs/CI_RELEASE_EVIDENCE.md`.

---

# S2 — PostgreSQL Production-Readiness

## Objective

Remove the SQLite-vs-PostgreSQL uncertainty.

## Tasks

- Run the complete application test suite against PostgreSQL.
- Exercise migrations from empty database.
- Exercise migrations against representative populated data.
- Test rollback/re-apply behavior where supported.
- Test enum creation/idempotency behavior.
- Test transactions and isolation.
- Test foreign-key enforcement.
- Test indexes and query plans for critical paths.
- Test tenant isolation against PostgreSQL specifically.
- Test concurrent requests where database locking matters.
- Test corpus reseed/build/swap behavior using PostgreSQL-backed application state.
- Identify all SQLite-only assumptions.

## Acceptance criteria

- No known SQLite/PostgreSQL behavioral discrepancy remains unexplained.
- PostgreSQL suite is reproducible locally/CI.
- Critical queries have acceptable execution plans.
- Tenant isolation passes under PostgreSQL.

---

# S3 — Aurora Deployment Rehearsal

## Objective

Prove that the actual production database can be created and upgraded.

## Owner dependency

AWS credentials/access and infrastructure decisions are **OWNER/AWS** work.

## Claude Code tasks

Prepare:

- exact migration procedure;
- pre-deploy checklist;
- post-deploy verification;
- rollback procedure;
- database health checks;
- smoke-test suite;
- release identity verification;
- application startup verification;
- failure recovery procedure.

## Owner/AWS tasks

- Provision Aurora/PostgreSQL.
- Configure networking/security groups/secrets.
- Apply migrations.
- Run smoke tests.
- Record timing and resource behavior.

## Acceptance criteria

- Real Aurora accepts the migrations.
- Existing/populated-data migration path is proven.
- Application can boot against Aurora.
- Smoke tests pass.
- Rollback/recovery procedure is documented and rehearsed.

---

# S4 — Backup & Disaster Recovery Proof

## Objective

Turn backup claims into demonstrated recoverability.

## Tasks for Claude Code

- Document RDS/Aurora backup architecture.
- Define RPO/RTO targets for owner approval.
- Create a restore verification script/checklist.
- Define post-restore application validation.
- Verify corpus fingerprint after restore.
- Verify release identity after restore.
- Verify tenant isolation after restore.
- Verify critical application reads/writes after restore.
- Document what is and is not covered by database backups.

## Owner/AWS task

Perform an actual backup restore into a controlled environment.

## Acceptance criteria

A restore has been performed, not merely configured.

The restored system passes:

- schema verification;
- application smoke tests;
- corpus/index identity checks;
- tenant isolation checks.

---

# S5 — Security & Privacy Release Hardening

## Objective

Prepare the application for real users and real data.

## Tasks

### Secrets

- Search git history and working tree for exposed secrets.
- Confirm `INDIAN_KANOON_API_KEY` rotation is complete.
- Add/verify secret scanning.
- Verify production secrets are injected through approved mechanisms.
- Ensure secrets are never logged.

### Authentication/authorization

- Re-run IDOR/tenant-isolation tests.
- Audit every tenant-scoped endpoint.
- Test privilege escalation paths.
- Test session/token expiry.
- Test unauthorized resource enumeration.

### LLM safety

- Enumerate every LLM egress.
- Prove consent is checked at each boundary.
- Test withdrawal behavior.
- Test malformed/missing consent state.
- Test citation withholding under adversarial output.

### Privacy

- Identify PII collection and storage.
- Identify retention/deletion behavior.
- Audit logs for accidental PII/secrets.
- Document data flows.

## Acceptance criteria

- Security review package is complete.
- No known critical secret exposure remains.
- Consent and tenant isolation are adversarially tested.
- Human security/privacy gate is ready.

---

# S6 — Corpus Integrity Hardening

## Objective

Make the corpus checks answer the question:

> “Is this actually the law we intended to ingest?”

not merely:

> “Does a section-shaped chunk exist?”

## Known baseline issues

The audit explicitly records:

- Stamp ss.8B/8E/8F/23A are unaddressable due to merged text.
- `it_act_2000` has a footnote/continuation parsing problem.
- `legal_services_1987` has a related continuation problem.
- Mediation ss.49/55 remain absent.
- Constitution Schedules 1–6, 8, 9, 11, 12 are not ingested.
- IPC 354E has duplicate section-number ambiguity.
- Some repealed ToP sections intentionally return nothing.
- `PENDING_LEGAL_REVIEW` decisions must remain explicit.

## Tasks

- Strengthen `test_corpus_contamination`.
- Add known-bad fixtures for every historical contamination pattern.
- Add source-to-corpus provenance assertions.
- Add negative tests: an amending Act must not masquerade as the principal Act.
- Add section-number collision detection.
- Add duplicate provision detection.
- Add schedule namespace validation.
- Add repealed-section semantics tests.
- Add corpus diff reports between fingerprints.
- Add upstream-source drift detection.

## Acceptance criteria

A corrupted or substituted legal provision causes a deterministic failure.

---

# S7 — Parser Recovery Sprint

## Objective

Recover known legitimate provisions without introducing new corpus corruption.

## Workstream A — Stamp Act

Investigate suffix handling for:

- s.8B
- s.8E
- s.8F
- s.23A

Do not flatten suffix sections into neighboring base sections.

## Workstream B — IT Act

Investigate footnote-aware continuation.

The audit states that the attempted recovery destroys a large Definitions corpus.
Therefore:

- reproduce the issue;
- identify PDF/text extraction boundaries;
- build a minimal fixture;
- implement parser logic;
- compare before/after corpus counts;
- run semantic/provenance checks.

## Workstream C — Legal Services Act

Use the same discipline as IT Act.

## Workstream D — Mediation Act

Investigate ss.49 and 55 while proving that ss.64 and 65 remain intact.

## Workstream E — Constitution Schedules

This is an **OWNER + LEGAL** decision first:

- ingest;
- or explicitly document the gap.

Claude Code must not decide this silently.

## Workstream F — IPC 354E

Mark and preserve `PENDING_LEGAL_REVIEW` until a qualified reviewer resolves the duplicate.

## Acceptance criteria

Every recovered provision has:

- source evidence;
- parser test;
- regression test;
- provenance;
- corpus fingerprint update;
- legal-review flag where required.

---

# S8 — Performance, Rate Limiting & Observability

## Objective

Make the system safe under real traffic.

## Rate limiting

The audit says rate limiting is currently per-process.

Claude Code should:

- locate every rate limiter;
- document the current semantics;
- add tests proving the limitation;
- design shared rate limiting;
- implement Redis/shared state only after owner approval;
- test horizontally scaled instances.

Until shared rate limiting is proven, deployment documentation must explicitly prohibit
horizontal scaling.

## Performance

- Benchmark SQLite vs PostgreSQL.
- Benchmark search/retrieval latency.
- Benchmark citation validation.
- Benchmark corpus reseed.
- Benchmark startup/preflight.
- Identify N+1 queries.
- Capture slow queries.
- Add performance regression thresholds for critical paths.

## Observability

Implement or wire:

- error tracking;
- structured application logs;
- health endpoint/check;
- readiness endpoint/check;
- database health monitoring;
- alerting;
- deployment smoke tests;
- critical failure alerts.

Owner chooses the error tracker/alert destination.

## Acceptance criteria

- Critical failures generate actionable alerts.
- Performance baselines are recorded.
- Horizontal scaling is either safe or explicitly blocked.

---

# S9 — Release Engineering & Canary

## Objective

Make deployment repeatable and reversible.

## Tasks

- Verify `RELEASE.json` generation.
- Verify corpus fingerprint pinning.
- Verify preflight fail-closed behavior.
- Add release artifact generation.
- Add deployment manifest/checklist.
- Add smoke-test command.
- Add canary procedure.
- Add rollback procedure.
- Add migration compatibility checks.
- Add deployment audit record.
- Ensure application refuses incompatible corpus/index combinations.
- Ensure an un-audited tree cannot deploy.

## Adversarial tests

Intentionally test:

- modified source after release identity generation;
- modified corpus;
- modified vector index;
- wrong environment;
- missing secret;
- prohibited feature enabled;
- stale migration;
- incompatible release identity.

Every one should fail closed.

---

# S10 — Human / Legal Gate Package

## Objective

Turn the audit's human gates into reviewable evidence packages.

Claude Code prepares evidence. Humans decide.

## G1 — Corpus authenticity

Package:

- corpus manifest;
- source provenance;
- known-good/known-bad results;
- contamination test results;
- unresolved legal-content issues;
- corpus fingerprint;
- changes since previous review.

## G6/G7 — Security & privacy

Package:

- threat model;
- data-flow summary;
- tenant isolation evidence;
- consent evidence;
- secret scan;
- dependency/security scan;
- logging review;
- retention/deletion behavior.

## Hallucination sign-off

Package:

- adversarial prompts;
- citation validation results;
- withheld-answer examples;
- unsupported-claim tests;
- malformed-citation tests;
- retrieval failure tests;
- human-review sample set.

## Acceptance criteria

Each human gate has:

- named reviewer;
- date;
- decision;
- evidence;
- unresolved issues;
- explicit GO/NO-GO.

---

# S11 — Final Adversarial Release Audit

## Objective

Attempt to break the release before the owner does.

## Claude Code should use subagents/parallel workstreams for independent audits:

### Agent A — Corpus attacker

Try to discover:

- wrong statutory text;
- amending-law contamination;
- duplicate sections;
- missing provisions;
- bad schedules;
- broken provenance;
- stale corpus.

### Agent B — Security attacker

Try:

- IDOR;
- tenant crossing;
- privilege escalation;
- secret leakage;
- prompt injection through retrieved legal text;
- consent bypass;
- citation bypass.

### Agent C — Reliability attacker

Try:

- failed migrations;
- interrupted reseed;
- corrupt index;
- disk exhaustion;
- stale release;
- partial deployment;
- restart during lock/rebuild.

### Agent D — CI/CD attacker

Try:

- bypassing release checks;
- hiding test failures;
- running with an unpinned dependency;
- deploying from the wrong commit;
- breaking history-dependent checks.

### Agent E — Product trust attacker

Try:

- unsupported legal answers;
- hallucinated citations;
- citations to wrong provisions;
- stale corpus answers;
- answers produced when grounding is unavailable.

## Acceptance criteria

Every finding is:

- fixed;
- accepted with explicit owner sign-off;
- or blocks release.

No “known issue” may silently disappear.

---

# S12 — Production Launch

## GO criteria

Launch only when all are true:

- [ ] CI green on the release commit.
- [ ] SQLite suite green.
- [ ] PostgreSQL suite green.
- [ ] Aurora migration proven.
- [ ] Backup restore proven.
- [ ] Production secrets rotated and correctly configured.
- [ ] Repo exposure addressed.
- [ ] Security/privacy review complete.
- [ ] Corpus authenticity human gate complete.
- [ ] Hallucination/citation safety sign-off complete.
- [ ] Release identity verified.
- [ ] Corpus fingerprint verified.
- [ ] Vector index fingerprint verified.
- [ ] Rate limiting is production-safe.
- [ ] Monitoring and alerting are live.
- [ ] Rollback procedure rehearsed.
- [ ] Canary smoke test passes.
- [ ] Owner gives explicit GO.

## NO-GO triggers

Any of the following blocks launch:

- red CI;
- untested production database;
- untested restore path;
- unresolved critical security issue;
- unresolved legal authenticity issue;
- citation gate bypass;
- tenant isolation failure;
- consent bypass;
- release identity drift;
- stale/corrupt corpus or index;
- unknown production migration state.

---

# 4. Claude Code Definition of Done

A sprint is **DONE** only when:

1. the implementation exists;
2. the tests exist;
3. the tests fail before the fix where practical;
4. the tests pass after the fix;
5. regression coverage exists;
6. the diff has been reviewed;
7. security implications have been considered;
8. documentation has been updated;
9. release/corpus fingerprints are updated where applicable;
10. remaining uncertainty is explicitly recorded;
11. the change is committed.

“Code written” is not “sprint complete.”

---

# 5. Suggested Claude Code Prompt

Use this as the master instruction when starting a sprint:

> You are working on Juriscite, an Indian legal research application.
>
> Read `FINAL_AUDIT_2026-07-31.md` and `CLAUDE_CODE_SPRINTS.md` before making changes.
>
> First inspect the repository and current git state. Do not assume the audit is still
> current; verify its claims against the code and tests.
>
> Work only on the requested sprint.
>
> Follow the project rules:
> - fail closed;
> - never weaken tests;
> - never invent legal text;
> - preserve provenance;
> - preserve tenant isolation;
> - preserve consent enforcement;
> - preserve citation withholding;
> - never silently resolve legal ambiguity;
> - do not implement governance-deferred features.
>
> Use repository search, git history, focused tests, full regression tests, static analysis,
> and parallel investigation/subagents where useful.
>
> Before editing, give a concise plan.
>
> Reproduce the relevant failure or establish a baseline.
>
> Implement the smallest safe change.
>
> Add regression tests that would have caught the original problem.
>
> Run focused tests, then the appropriate complete suite.
>
> Attempt an adversarial test against the new control.
>
> Review the final diff for security, data-integrity, migration, and release implications.
>
> Update documentation and audit evidence.
>
> Commit the completed work in a coherent commit.
>
> At the end report:
> 1. files changed;
> 2. behavior changed;
> 3. tests run and exact results;
> 4. adversarial checks;
> 5. commit SHA;
> 6. remaining risks;
> 7. owner/legal/AWS decisions required.
>
> If the task requires an OWNER, LEGAL, SECURITY, AWS, or BILLING decision, stop at that
> boundary and clearly state what evidence you prepared and what decision is required.

---

# 6. Recommended Execution Order

Claude Code should execute in this order:

```text
S0 Baseline
  ↓
S1 CI Green
  ↓
S2 PostgreSQL Proof
  ↓
S3 Aurora Rehearsal
  ↓
S4 Backup Restore
  ↓
S5 Security/Privacy
  ↓
S6 Corpus Integrity
  ↓
S7 Parser Recovery
  ↓
S8 Performance/Rate Limits/Observability
  ↓
S9 Release Engineering
  ↓
S10 Human Gates
  ↓
S11 Adversarial Audit
  ↓
S12 GO / NO-GO
```

S6/S7 may proceed in parallel with S3/S4 where they do not alter the production release
branch, but production deployment should remain blocked until the P0 gates are closed.

---

# 7. Immediate Next Three Claude Code Sessions

## Session 1 — S0 + S1

**Mission:** establish baseline and make CI genuinely green.

Do not touch legal corpus content.

Deliver:

- baseline report;
- CI fixes;
- green CI;
- regression test proving CI can fail;
- commit(s).

## Session 2 — S2

**Mission:** prove PostgreSQL behavior end-to-end.

Deliver:

- PostgreSQL test coverage;
- migration tests;
- populated-database migration test;
- transaction/concurrency findings;
- SQLite/PostgreSQL discrepancy report;
- commit(s).

## Session 3 — S6

**Mission:** strengthen corpus integrity before attempting parser recovery.

Deliver:

- contamination fixtures;
- duplicate-section detection;
- schedule namespace checks;
- provenance checks;
- corpus diff tooling;
- explicit unresolved corpus list.

Only after S6 is stable should Claude Code aggressively attempt S7 parser recovery.

---

# 8. What Claude Code Must NOT Do

Do not let Claude Code:

- declare the corpus legally correct;
- decide whether Constitution Schedules should be included;
- decide whether IPC 354E is legally one provision or two;
- silently "fix" statutory text based on model knowledge;
- use web content as a substitute for official corpus provenance;
- enable live billing;
- enable Kanoon grounding by default;
- ingest a judgment corpus;
- scrape eCourts;
- build judge/person prediction or scoring;
- remove release gates because they are inconvenient;
- turn warnings into passes;
- skip PostgreSQL because SQLite passes;
- declare backups safe without a restore;
- declare security complete without human review;
- declare legal safety complete without qualified human review.

---

# 9. Release Philosophy

The project has already demonstrated that apparently strong checks can be wrong.

The central engineering principle for the next stage is therefore:

> **Every important control must have a demonstrated failure mode.**

For every gate ask:

1. What is this gate supposed to catch?
2. Can we deliberately create that failure?
3. Does the gate actually fail?
4. Can the failure be bypassed?
5. Is the evidence reproducible?
6. Is the result persisted in CI/release evidence?

The objective is not to make Juriscite look production-ready.

The objective is to make it **difficult for an unsafe release to appear production-ready**.

---

# 10. Current Release Position

Based strictly on the 2026-07-31 audit:

**Engineering maturity:** strong pre-release foundation.

**Production status:** NOT READY.

**Most important immediate work:**

1. CI genuinely green.
2. PostgreSQL/Aurora proof.
3. Backup restore proof.
4. Security/privacy gates.
5. Corpus authenticity review.
6. Citation/hallucination human sign-off.
7. Operational observability.
8. Final adversarial audit.

The project should move toward release through **evidence-producing sprints**, not feature-count
sprints.
