# Incident & Data-Breach Response Policy (LSAI-LEGAL-15)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23
Aligns with DPDP Act 2023 breach-notification duties (to the Data Protection Board and affected
data principals) and SC AI-in-Courts Regs 2026 accountability principles.

## Scope
Any confidentiality/integrity/availability incident affecting user, client, or matter data, or the
AI system producing materially unsafe output.

## Severity
- **P0** — cross-tenant data leak, credential/key compromise, data loss, public exposure of client data.
- **P1** — auth/RBAC bypass, integrity bug affecting many records, prolonged outage.
- **P2** — limited-impact bug, single-record issue, contained config error.

## Process
1. **Detect & record** — open an incident entry (time, severity, systems, data categories, tenant(s)).
2. **Contain** — revoke keys/tokens, isolate, stop-the-line on related feature work.
3. **Eradicate & recover** — fix root cause; restore from `BackupRun` if needed.
4. **Assess notification duty** — Founder + counsel decide DPDP notification to the Board + affected
   users (timing/content per the Act). **[MISSING / TO BE POPULATED: exact timelines on counsel advice]**.
5. **Notify** affected users where required; never conceal a reportable breach.
6. **Post-incident review** — write up cause, fix, and a prevention test; add the test to the suite.

## Roles
- Incident lead: **Founder** (until a security owner is appointed — **[MISSING]**).
- Security reviewer (G7) sign-off required before real client data.

## Standing safeguards already in place
Tenant isolation (P0 invariant + tests), audit log, field encryption at rest, automated backups,
HTTP security headers, no secrets in repo.

_Draft execution artifact; SOP requires security-reviewer + counsel sign-off (G7)._
