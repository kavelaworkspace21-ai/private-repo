# Misuse & Abuse Reporting Policy (LSAI-LEGAL-16)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23

How users report misuse, and how we respond. Required for safe operation and app-store compliance
(a clear, in-product way to report abuse / objectionable content).

## How to report
- In-product: any signed-in user can file a report via `POST /api/misuse/` (categories: abuse,
  security, objectionable_content, impersonation, other) with a subject + details.
- Reports are tenant-scoped, audited, and visible to the reporter (`/api/misuse/mine`) and to firm
  admins (`/api/misuse/`).
- Email channel for non-users / urgent reports: **[MISSING / TO BE POPULATED: grievance email]**.

## How we respond
1. Acknowledge and triage (status `received` → `in_review`).
2. Investigate; consult the Acceptable Use Policy and safety doctrine.
3. Act — warn, restrict, deactivate a member (`is_active=false`), remove content, or escalate to the
   Incident process for security issues. Status → `actioned` or `dismissed` with a resolver note.
4. Audit every step (`misuse_report` / `misuse_update` actions).

## Enforcement options
- Member deactivation (firm admin) preserves audit/authored data.
- Account erasure on request (DPDP) via `DELETE /api/account`.
- AI misuse (asking the AI to help with unlawful acts) is refused at the input screen
  (`safety.screen_request_intent`) and may be reported here.

## Tracker
Backed by the `MisuseReport` model + `tests/test_misuse_reports.py`.
