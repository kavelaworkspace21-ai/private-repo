# eCourts Integration Policy (LSAI-LEGAL-11)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23

How LegalServer.AI integrates court data — lawfully and minimally.

## Authorised scope (2026-06-19)
- **Read-only** access to a matter's hearing data **via the official / authorised eCourts API**.
- Pull hearing dates into the **Court Diary**; export the diary to the user's calendar (`.ics`).

## Hard prohibitions (never implement)
- **No web scraping** of eCourts or any court portal.
- **No CAPTCHA solving / bot-detection bypass.**
- No automated bulk harvesting; no writes/filings via this path.
(Per `CLAUDE.md §12` and the Acceptable Use Policy.)

## Safe-by-default behaviour
- The connector is **inert unless `ECOURTS_API_BASE` is configured** (feature-flagged).
- When unconfigured it **degrades gracefully**: the UI says "eCourts API not configured yet — you can
  still add hearings manually." No errors, no partial scraping fallback.
- Data fetched is limited to the matter's own hearing schedule (data minimisation).

## Guardrails
- `tests/test_ecourts_compliance.py` asserts the eCourts code contains no scraping/CAPTCHA/headless-
  browser tooling and that the integration is read-only + flag-gated.
- The Acceptable Use Policy forbids scraping/CAPTCHA bypass (`test_legal_policy_routes.py`).

## Open items
- Confirm the exact authorised API endpoint + terms with the eCourts/NIC programme — **[MISSING /
  TO BE POPULATED]** (`ECOURTS_API_BASE` unset until confirmed).
