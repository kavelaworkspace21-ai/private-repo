# Incident Runbook

For security/privacy incidents affecting Juriscite. Regulatory timers are hard: **CERT-In — 6 hours**
(cyber incident, per CERT-In Directions 2022) and **DPDP — Data Protection Board (DPB) notification**
plus affected-user notice (initial without delay, detailed follow-up). Confirm the exact current DPDP
Rules text with counsel — `[counsel confirms]`. Nothing here is legal advice.

## Severity

| Sev | Definition | Examples |
|---|---|---|
| **SEV-1** | confirmed breach of personal data / cross-tenant exposure / auth bypass | tenant A reads tenant B's matter; DB exfiltration; key leak |
| **SEV-2** | credible threat, no confirmed data loss | targeted brute force; a critical CVE actively exploitable; failed backups |
| **SEV-3** | contained/low-impact | single stuck job; isolated 5xx; a waived-CVE reminder |

## Roles

Incident Lead (owner) · Eng responder · Privacy/legal (counsel) · Comms. In a solo/early setup the
owner holds all roles but must still hit the regulatory clocks.

## Detection sources (what exists)

- **Audit log** (`app/models/audit.py`, `AuditLog`) — auth/admin/data-rights/billing actions.
- **Misuse reports** (`app/models/misuse_report.py`) — flagged abuse / soul-ejection events.
- **Structured logs + request IDs** (`app/observability.py`); optional Sentry (`SENTRY_DSN`).
- **Scheduled-job health** — `scheduler.stale_jobs()` (missed backups/reminders/drift).
- **Corpus drift + currency** — `check_upstream()` (`UPDATED_UPSTREAM` / `UNVERIFIED`).
- **Health** — `/healthz`, `/readyz`. 🔒 Alert-channel routing (email/Slack) is owner-gated (OWNER-12).

## Response

1. **Identify & record** — open an incident record (time, reporter, severity, systems). Start the
   clock the moment a personal-data breach is *suspected* (don't wait for confirmation).
2. **Contain** — revoke sessions/keys as needed; isolate the affected instance; for a leaked secret,
   rotate it (see key-rotation) and invalidate tokens. Do NOT destroy evidence — snapshot logs first.
3. **Assess scope** — which tenants/records/personal-data categories (use `PRIVACY_DATA_FLOW.md`);
   was data read, exfiltrated, or altered; is it ongoing.
4. **Notify (regulatory clocks — SEV-1 personal-data breach):**
   - **CERT-In within 6 hours** of noticing a reportable cyber incident (template below).
   - **DPB** — notify without delay, detailed follow-up per the DPDP Rules `[counsel confirms]`.
   - **Affected users** — clear notice of what happened, data involved, and steps to take.
5. **Eradicate & recover** — patch root cause; restore from a **verified** backup
   (`BACKUP_RESTORE_RUNBOOK.md`); rebuild the index from fulltext if integrity is in doubt
   (`reseed()` + `release preflight`).
6. **Post-incident** — timeline, root cause, corrective actions, and a test/monitor so it can't recur.

## CERT-In report template (≤6h)

```
Organisation / contact:
Time incident noticed (IST):
Type: [unauthorised access / data breach / auth bypass / DoS / other]
Affected systems: [app / DB / vector store / EC2 / subprocessor]
Description & timeline:
Data involved (categories, approx. count):
Actions taken (containment):
Current status: [ongoing / contained / resolved]
```
NTP time sync + ≥180-day security-log retention are CERT-In requirements — see the logging/retention
config and `docs/OWNER_QUEUE.md`.

## DPB / affected-user breach notice template

```
Nature of the personal-data breach:
When it occurred / was discovered:
Categories & approximate number of data principals affected:
Likely consequences:
Measures taken / proposed (containment, mitigation):
Contact point for data principals:
```

## Owner prerequisites (🔒, before this runbook is fully executable)

- CERT-In reporting contact + process registered; NTP configured on hosts.
- Alert channel wired to `stale_jobs()` / health / audit anomalies (OWNER-12).
- Counsel-confirmed DPDP breach thresholds + exact DPB template.
- A rehearsed tabletop of one SEV-1 personal-data breach (feeds G6/G7 evidence).
