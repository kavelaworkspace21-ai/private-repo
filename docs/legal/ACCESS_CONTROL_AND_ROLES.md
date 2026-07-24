# Access Control, Roles & Advocate Verification (LSAI-LEGAL-07)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23

Who can do what, and how we keep the platform to verified advocates/firms (not the general public).

## Roles
| Role | Purpose | Matter data | Firm admin | AI research/drafting | 2FA required |
|---|---|---|---|---|---|
| `firm_admin` | Owns the firm workspace; manages members & verification | Read/write | Yes | Yes | Yes |
| `advocate` | Practising advocate | Read/write | No | Yes | Yes |
| `associate` | Junior advocate | Read/write | No | Yes | No |
| `clerk` | Support staff | **Read-only** | No | No (by policy) | No |
| `judge` | Reserved (not a firm matter manager) | No | No | Per policy | Yes |
| `business` | Reserved (non-advocate org) | No | No | Per policy | Yes |

Enforced by `require_role` / `require_matter_write` / `require_firm_admin` in
`app/auth/dependencies.py`. Cross-tenant access is denied (404) — tenant isolation is a P0 invariant.

## Founder / super-admin
There is no in-app super-admin role. **Founder-only** cross-tenant actions (advocate verification)
are guarded by `require_founder` using the `ADMIN_TOKEN` secret via the `X-Admin-Token` header.
If `ADMIN_TOKEN` is unset, those actions fail closed (denied).

## Advocate / firm verification
- A firm admin submits jurisdiction + Bar enrolment reference: `POST /api/firm/verification`
  → tenant `verification_status = pending`.
- The founder reviews and decides: `PATCH /api/admin/verify/{tenant_id}` (`verified|rejected|pending`).
- Status is visible to members: `GET /api/firm/verification`.
- For the closed beta, verification is **founder-approved manually** (no automated Bar-registry check).

## AI access gate
- Feature flag `AI_REQUIRES_VERIFICATION` (default **OFF** for the closed beta).
- When **ON**, AI legal research (`POST /api/ai/chat`) and drafting (`POST /api/drafting/generate`)
  require a `verified` tenant; unverified tenants receive a clear `403` (`require_ai_access`).
- This keeps AI legal tooling restricted to verified advocates/firms once enabled, consistent with
  "for advocates & law firms only — not a public legal-advice service."

## Open items
- Automated Bar Council enrolment verification — **[MISSING / TO BE POPULATED]** (manual for beta).
- Per-tenant AI enable/disable toggle — **[MISSING / TO BE POPULATED]**.
