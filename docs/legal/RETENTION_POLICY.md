# Data Retention Policy — LegalServer.AI

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23
Mirrors `app/services/privacy.py::RETENTION_POLICY` (the enforced runtime policy).

| Data | Retention |
|---|---|
| Matter data (clients, cases, hearings, fees, documents, drafts) | Retained until the advocate deletes it or requests account erasure. Legal limitation periods require long retention. |
| Audit logs | Retained for accountability; not auto-deleted (removed only on erasure). |
| Read notifications | Auto-purged 90 days after being read. |
| Account on erasure | Account + all tenant data irreversibly deleted (DPDP right to erasure), audited first. |
| Backups | Rolling retention of the most recent backups (`BACKUP_KEEP`, default 7). |

## Notes
- Erasure may need to reconcile with lawful/accounting retention once billing is enabled; such records
  may be anonymised or retained as legally required (**[detail: MISSING / TO BE POPULATED]**).
- A firm member cannot delete the whole firm's tenant data without the firm-admin erasure flow.

_Draft execution artifact; final periods require DPDP-reviewer/counsel confirmation._
