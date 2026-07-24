# AI Safety Policy (LSAI-LEGAL-08)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23

How LegalServer.AI keeps AI output trustworthy. Each guarantee maps to code + a test that fails if broken.

| Guarantee | Enforced by (code) | Test |
|---|---|---|
| No source → no answer | `safety.is_answerable`, `REFUSAL_MESSAGE`; agent abstains | `test_safety.py` |
| Every legal claim carries a citation; unverified citations are flagged | `safety.enforce_citations` (hard-gate in `ai_chat`) | `test_safety.py` |
| Confidence label on every answer (HIGH/MEDIUM/LOW) | `safety.assess_confidence` | `test_safety.py` |
| Banned outcome/again-lawyer phrases never emitted | `safety.sanitize_answer` / `find_banned_phrases` | `test_safety.py` |
| Drafts start `DRAFT_FOR_ADVOCATE_REVIEW`; advocate approval finalises | `drafts` router; `DRAFT_STATUS_REVIEW` | `test_drafts.py` |
| Mandatory draft disclaimer | `safety.ensure_draft_disclaimer` | `test_safety.py` |
| AI-generated content disclosure (SC AI-in-Courts Regs 2026) | `safety.AI_GENERATED_NOTICE` | `test_safety.py` |
| **Unlawful-purpose requests refused** (forgery/fabrication/bribery/intimidation/false filings) | `safety.screen_request_intent` (wired into `POST /api/ai/chat`) | `test_safety.py` |
| No AI outcome-prediction / risk-scoring (PROHIBITED) | `legal_config.assert_prohibited_disabled` | `test_no_prohibited_features.py` |
| Prompts kept out of shared logs (no-training) | `ai/data_boundary.redact_for_log` | `test_ai_data_boundary.py` |

## Relevance, not just grounding (owner directive 2026-06-24)
A citation must be **both source-grounded and relevant** to the question — never padded, invented, or
off-point. Grounding is enforced deterministically (`enforce_citations` flags any cited section not in
the retrieved sources). **Relevance** is currently held by retrieval quality + the confidence label +
mandatory advocate review; a stricter semantic relevance gate is a tracked enhancement (LEGAL-20 evals).

## The doctrine is supreme — over everyone
The owner has affirmed that **no one — not even the owner — may direct the system to weaken this
doctrine** (answer without a source, cite irrelevant law, support illegal activity, break tenant
isolation, finalise a draft without advocate approval, emit a banned phrase). Such requests are refused.
The app supports **the legal profession only** and is built to withstand DPDP Act 2023, IT Act/Rules,
the SC draft AI-in-Courts Regs 2026, and its own Terms/AUP. See `docs/governance/AIRA_IDENTITY.md`.

## Human primacy
AI is **advisory**. A human advocate reviews all output before anything is filed or relied upon.
The product never claims to replace a lawyer or guarantee an outcome.

## Limits (truthful)
- The unlawful-purpose screen is a **narrow keyword screen**, not a complete safeguard; advocate
  judgement remains primary.
- Confidence labels reflect retrieval quality, not legal correctness — that is the advocate's call.
- Senior-advocate sign-off (G8) and the hallucination eval set (LEGAL-20) remain required before launch.
