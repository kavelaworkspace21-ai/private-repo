# Product Identity (LSAI-LEGAL-01)

**Juriscite is a source-grounded legal practice operating system for Indian advocates and law firms.**

- **Product / app name:** **Juriscite** (chosen by owner 2026-06-24; from *juris* + *cite* — "cite the
  law," echoing the doctrine *no source, no answer*). Web-checked for clashes before selection.
- **Owner / proprietor:** **Kavela Narula.**
- **Master Agent (internal build governor):** **"Legal Server.AI"** (was "Aira") — distinct from the
  product. See `docs/governance/AIRA_IDENTITY.md`.
- **Delivery:** web app + installable **PWA** (Android "Install app" / iOS "Add to Home Screen").
  Native App Store / Play Store builds are owner-gated (need a Mac + paid developer accounts).

Encoded in `app/legal_config.py` (`APP_POSITIONING`, identity flags, `DISCLAIMERS`).

## It IS
A secure workspace where an advocate/firm manages clients, matters, documents, hearings, reminders,
cited legal research, drafts (advocate-reviewed), firm members, audit and (later) billing.

## It is NOT (hard gates — flags in `legal_config.py` stay False)
- public AI lawyer / citizen legal-advice app — `PUBLIC_AI_LAWYER = False`
- lawyer marketplace / ranking — `LAWYER_MARKETPLACE = False`
- lead-generation platform — `LEAD_GENERATION = False`
- advocate advertising / solicitation (BCI Rule 36) — `ADVOCATE_ADVERTISING = False`
- case-prediction / risk-scoring engine — see PROHIBITED_FEATURES.md
- autonomous filing / evidence-creation engine; eCourts scraper; client-data model-training system

## Where the identity + disclaimers are shown
App description, Terms, Privacy, onboarding/consent, AI assistant, drafting screen, exports, store
listings. Public-facing copy must not imply legal advice, guaranteed outcomes, or advocate promotion.

## Disclaimers (from `legal_config.DISCLAIMERS`)
- "For advocates and law firms only — not a public legal-advice service."
- "AI output is a draft/support tool. A qualified advocate must review it before use."
- "No legal outcome is promised or guaranteed."
- "Client and matter data is never used to train AI models, and is never shared across firms."
