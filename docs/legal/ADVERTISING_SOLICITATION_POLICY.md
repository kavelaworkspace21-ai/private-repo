# Advertising & Solicitation Policy (LSAI-LEGAL-10)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23
Aligns with **Bar Council of India Rules, Rule 36** (restrictions on advocate advertising/solicitation)
and the product identity: a **private practice tool for advocates**, not a public-facing legal marketplace.

## What the product is NOT (and will not become without ethics review)
LegalServer.AI does **not** implement, and must not implement without senior-advocate ethics review:
- A public lawyer **directory / marketplace** or "find a lawyer" feature.
- **Lead generation** / client solicitation for advocates ("get more clients", "win more cases").
- **Ranking, rating, or comparison** of advocates to the public.
- Touting, advertisements of services, or any feature that solicits work on an advocate's behalf.
- Public claims of success rate, guaranteed outcomes, or testimonials used as advertising.

These are deferred-or-prohibited per `CLAUDE.md §1` and barred by the safety doctrine
(no "you will win"/"guaranteed"/"replaces a lawyer" language — `test_safety.py`).

## What the product IS
A closed, per-firm workspace for verified advocates to manage their own clients, matters, court
diary, cited research, and drafts. It is **not a public legal-advice service** (stated in `/legal`
and the footer on every page).

## Guardrails
- UI carries no solicitation/marketplace surfaces — guarded by `tests/test_solicitation_guard.py`.
- The no-prohibited-features guard (`tests/test_no_prohibited_features.py`) blocks prediction/ranking
  language from reappearing.
- Any future outward-facing/marketing surface requires **senior-advocate ethics review** (G8) first.

_Draft execution artifact; final review by a senior advocate required (Rule 36 is fact-sensitive)._
