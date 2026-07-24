# AI Data Boundary Policy (LSAI-LEGAL-06)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23

How client/matter data is handled when AI features are used.

## No training on your data
Client and matter data is **never** used to train or fine-tune AI models. Prompts are sent to the AI
provider only to produce the output you requested, and are not contributed to any training set.
(Enforced operationally; the provider contract/region is recorded in the Subprocessor Register.)

## Single controlled path
All AI provider calls go through one configured client (`app/ai/llm_config.py` → `ai_config()` used by
`app/ai/agent.py`, `app/routers/ai_drafting.py`, `app/routers/library.py`, `app/ai/case_law.py`). There
is no other outbound AI path. The provider is configurable (`AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL`).

## Data minimisation & logging
- Raw sensitive prompt text is **not written to application/server logs**. Log redaction is provided by
  `app/ai/data_boundary.py::redact_for_log()`.
- AI usage is auditable at the metadata level (who/when/what type) without dumping private content into
  shared logs.
- Retrieved corpus text used for grounding is public legal material, not client data.

## Tenant controls
- AI calls are tenant-scoped; one firm's data is never visible to another.
- (Optional, future) per-tenant AI enable/disable setting — **[MISSING / TO BE POPULATED]**.

## In-app notices
The AI assistant and drafting screens show: "Do not enter data unless authorised by your firm/client."
and "AI output requires advocate review."

_Draft execution artifact; final review by DPDP reviewer + senior advocate required._
