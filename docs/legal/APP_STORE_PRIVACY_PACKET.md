# App-Store Privacy Packet (LSAI-LEGAL-19)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23
Maps the product to **Google Play Data Safety** + **Apple App Privacy** labels. Single source of truth
for the data behaviour is `DATA_MAP_AND_STORE_DISCLOSURE_MATRIX.md` — keep them consistent.

> Note: mobile app is **deferred** (`CLAUDE.md §1`). This packet is prepared in advance so labels are
> accurate when/if a mobile or PWA build is submitted. **Do not submit until the data map is complete.**

## Declared data collection (summary)
- **Personal info**: name, email, phone — account & contact.
- **User content**: clients, matters, documents, hearings, fees, AI prompts/outputs — app functionality.
- **Financial info (user content)**: fee-ledger entries the advocate records (not payment data).
- **Identifiers / diagnostics**: IP + device/browser metadata — security & consent receipts.

## Key declarations
- Data is **encrypted in transit** (TLS) and sensitive fields at rest (field-level encryption).
- Users can **request deletion** (DPDP erasure: `DELETE /api/account`) and **export** their data.
- Data is **not sold**, **not shared for ads**, and **never used to train AI models**.
- No payment/financial-account data collected (billing disabled — LEGAL-18).

## Store readiness checklist (gates)
- [ ] Data map complete (no `MISSING` rows) — `DATA_MAP_AND_STORE_DISCLOSURE_MATRIX.md`.
- [ ] Privacy Policy URL live & reachable — `/legal/privacy`.
- [ ] Account deletion path documented for reviewers — `/account` + `DELETE /api/account`.
- [ ] Abuse/misuse reporting path — `/api/misuse` (LEGAL-16).
- [ ] Subprocessor list current — `SUBPROCESSOR_REGISTER.md`.
- [ ] Diagnostics/crash-logging declared accurately — **[MISSING]**.
- [ ] Senior-advocate (G8) + DPDP reviewer + security (G7) sign-off — **human gates, OPEN**.

_Draft execution artifact; final review by the store owner + DPDP reviewer required._
