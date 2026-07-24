# Human Sign-off Packet (LSAI-LEGAL-21)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23

The launch gates that **only a human** may approve. Code never self-certifies these (see
`legal_config.LAUNCH_GATES`, fail-closed). Each reviewer signs against the evidence listed.

| Gate | Reviewer (human) | What they certify | Evidence to review | Status |
|---|---|---|---|---|
| **G1** corpus authenticity | Senior Advocate | Retrieved sources are authentic & verbatim; titles correct | corpus viewer, `project_corpus_authenticity` | ☐ OPEN |
| **G6** privacy review | DPDP / privacy reviewer | Consent, retention, data map, rights, no-training all sound | `/legal`, data map, `/api/account/*`, `/api/data-rights` | ☐ OPEN |
| **G7** security review | Security reviewer | Tenant isolation, auth/RBAC, encryption, backups, headers, incident plan | isolation tests, `INCIDENT_RESPONSE_POLICY.md` | ☐ OPEN |
| **G8** AI behaviour + templates | Senior Advocate | Cited answers + drafting templates are safe and correct | `AI_SAFETY_POLICY.md`, eval suite, templates | ☐ OPEN |
| closed-beta validated | Founder | Advocates use it without hand-holding | beta feedback | ☐ OPEN |
| willingness to pay | Founder | Real demand signal | market evidence | ☐ OPEN |

## Sign-off block (to be completed by humans, not code)
- G1 — name / date / signature: **[MISSING]**
- G6 — name / date / signature: **[MISSING]**
- G7 — name / date / signature: **[MISSING]**
- G8 — name / date / signature: **[MISSING]**

**No real client data and no public launch until G6 and G7 are signed; no public AI-behaviour claims
until G1 and G8 are signed.** Recording approval is a controlled amendment (Founder + named reviewer).
