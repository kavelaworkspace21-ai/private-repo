# Data Map & Store Disclosure Matrix (LSAI-LEGAL-04)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23
Maps each data flow so the Privacy Policy, Google Play Data Safety, and Apple App Privacy labels match
actual code behaviour. **Store submission is blocked until this matrix is complete and reviewed.**

Legend — Shared: only with subprocessors to deliver the service; never sold; never used to train models.

| Data category | Collected | Source | Purpose | Linked to user | Shared | Subprocessor | Retained | User can delete | Google Data Safety | Apple App Privacy | Code location |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Name | Yes | User | Account, identity | Yes | Hosting | AWS | Until erasure | Yes (erasure) | Personal info → Name | Contact info → Name | `models/user.py` |
| Email | Yes | User | Auth, notices | Yes | Hosting, email | AWS, SMTP | Until erasure | Yes | Personal info → Email | Contact info → Email | `models/user.py` |
| Phone | Optional | User | Contact | Yes | Hosting | AWS | Until erasure | Yes | Personal info → Phone | Contact info → Phone | `models/user.py` |
| Password hash | Yes | User | Auth | Yes | No | AWS | Until erasure | Yes | App activity → none (excluded from export) | Not exported | `core/security.py` |
| Firm/tenant data | Yes | User | Workspace | Yes | Hosting | AWS | Until erasure | Admin flow | App info | App functionality | `models/tenant.py` |
| Advocate enrolment no. | Optional | User | Verification | Yes | Hosting | AWS | Until erasure | Yes | Personal info | Contact info | `models/user.py` (LEGAL-07) |
| Client names/contacts | Yes | User-entered | Matter mgmt | Yes (firm) | Hosting | AWS | Until firm deletes | Firm flow | User content | User content | `models/client.py` |
| Matter facts | Yes | User-entered | Matter mgmt | Yes (firm) | Hosting | AWS | Until firm deletes | Firm flow | User content | User content | `models/case.py` |
| Documents/uploads | Yes | User-uploaded | Storage/versioning | Yes (firm) | Hosting/storage | AWS | Until firm deletes | Firm flow | Files & docs | User content | `models/document*.py` |
| Court/hearing data | Yes | User/eCourts(opt) | Diary | Yes (firm) | Hosting | AWS | Until firm deletes | Firm flow | App activity | User content | `models/hearing.py` |
| Fees/billing data | Yes | User-entered | Fee tracking | Yes (firm) | Hosting | AWS | Until firm deletes | Firm flow | Financial info | Financial info | `models/fee.py` |
| AI prompts/outputs | Yes | User | Research/drafting | Yes | AI provider (transient) | Gemini | Per query record | Yes | App activity | Usage data | `ai/agent.py` |
| Audit logs | Yes | System | Accountability | Yes | Hosting | AWS | Until erasure | On erasure | App activity | Diagnostics | `models/audit.py` |
| Consent receipts | Yes | System | Proof of consent | Yes | Hosting | AWS | Until erasure | On erasure | App activity | Diagnostics | `models/consent.py` |
| IP address | Yes | Request | Security, consent receipt | Yes | Hosting | AWS | With audit/consent | On erasure | App activity | Identifiers | `routers/auth.py` |
| Device/browser metadata | Yes | Request | Security, consent receipt | Yes | Hosting | AWS | With consent | On erasure | App activity | Identifiers | `routers/auth.py` |
| Crash/diagnostic logs | **[MISSING]** | System | Debugging | **[MISSING]** | **[MISSING]** | **[MISSING]** | **[MISSING]** | **[MISSING]** | Diagnostics | Diagnostics | **[MISSING / TO BE POPULATED]** |
| Payment metadata | Not yet | — | Billing (future) | — | Gateway | **[MISSING]** | — | — | Financial info | Financial info | LEGAL-18 (not enabled) |
| Support tickets | Not yet | User | Support (future) | — | **[MISSING]** | **[MISSING]** | — | — | Messages | Customer support | **[MISSING]** |

**Open items marked `MISSING / TO BE POPULATED` must be resolved before R2 (real data) and store submission.**
