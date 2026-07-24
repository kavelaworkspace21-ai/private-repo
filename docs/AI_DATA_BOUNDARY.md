# AI Data Boundary

**Date:** 2026-07-24 · **Applies to:** Juriscite 0.2.0 and later
**Status of this control:** enforced in code and tested (`tests/test_ai_consent_boundary.py`)

What leaves this system when an advocate uses an AI feature, what authorises it, and what
is still missing. Written to be checkable — every claim below points at code or a test.

---

## 1. Where the boundary actually is

Most of Juriscite never leaves the machine it runs on. The boundary is crossed in exactly
two ways:

| Crossing | Destination | Carries client data? |
|---|---|---|
| **LLM generation** | NVIDIA NIM (`integrate.api.nvidia.com`), `meta/llama-3.1-70b-instruct` + fallback chain | **Yes** — the question, and any matter text or uploaded document the advocate includes |
| **Audio transcription** | configured Whisper-compatible provider (optional; unset by default) | **Yes** — the raw audio clip |

Two things that look like crossings but are not:

- **Embeddings / retrieval** run locally (ONNX MiniLM + ChromaDB). No query text is sent
  anywhere to be embedded.
- **Indian Kanoon** receives only a search phrase or a document id and returns public
  judgments. It is disabled by default (see `KANOON_ENABLED`) and its results are links
  shown to the advocate — never model grounding.

---

## 2. What authorises the crossing

**Consent, enforced at the boundary.** `require_ai_user` (in `app/auth/dependencies.py`)
guards all ten endpoints that can reach an LLM. It composes two checks:

1. **`require_ai_consent`** — unconditional. The user must have granted privacy consent at
   the **current** `PRIVACY_VERSION`. There is no environment flag to disable it, because
   "consent enforcement, disabled in production" is not consent.
2. **`require_ai_access`** — tenant verification, flag-gated on `AI_REQUIRES_VERIFICATION`
   (off during closed beta).

`has_current_consent()` in `app/services/privacy.py` is the single source of truth, used
both by the gate that blocks and by `/api/auth/needs-consent` that drives the UI banner —
so what the user is asked for and what actually blocks cannot drift apart.

**Who this stops.** Self-registered advocates consent at registration, so they are
unaffected. The real case is a **firm-invited member** — an admin creates the account, so
the member has granted nothing. Before this control they could use every AI feature without
ever having consented. Bumping `PRIVACY_VERSION` also invalidates prior consent by design,
forcing re-acceptance.

**What it deliberately does not block.** Only the AI boundary is gated. A user without
consent can still read their own matter data and reach `/consent`. Locking them out of
their own workspace would be a worse bug, and would make the consent page unreachable.

---

## 3. What is sent, and what is stripped

- **Retrieved statute text** is placed in a delimited source block declared the single
  source of truth for citations; injected instructions inside that block are contained as
  data (deterministic tests in `tests/test_prompt_injection.py`).
- **Prompt log redaction** (`app/ai/data_boundary.py`) keeps prompt contents out of
  application logs. Note this is a *logging* control — it does not reduce what is sent to
  the provider.
- **No training on client data.** Asserted in `NO_TRAINING_STATEMENT` and in the provider
  terms; it is a contractual control, not one this codebase can technically enforce.

---

## 4. Honest limitations

These are real and currently open. None is fixed by the consent gate.

1. **The consent is broad, not per-purpose.** One privacy-policy acceptance authorises all
   AI processing. DPDP favours specific, purpose-limited consent; a per-purpose model
   (research vs drafting vs document analysis) is not implemented.
2. **No consent receipt is surfaced at the moment of processing.** Consent is recorded with
   IP/user-agent/version and is auditable, but the advocate is not shown "this matter text
   will be sent to NVIDIA" at the point of sending.
3. **Third-party retention is not verifiable from here.** What the provider retains is
   governed by their terms, not by our code.
4. **Client consent vs advocate consent.** The advocate consents; their *client* — whose
   data is actually in the prompt — is not a party to it. This is a real question for G6
   privacy counsel, not something engineering can resolve.
5. **Deletion does not propagate to prompts already sent.** Erasure clears local rows; it
   cannot recall data already transmitted.

---

## 5. Verification

```bash
python -m pytest tests/test_ai_consent_boundary.py -q     # 9 tests
```

Covers: consent recorded at registration; stale policy version rejected; chat, drafting and
transcription blocked without consent; non-AI endpoints still reachable; access restored on
granting; and two structural guards — that **no** route takes verification without consent,
and that the known LLM handlers are gated by name (so a prefix change cannot silently empty
the check).

---

*Owner/human gates: G6 (privacy counsel) must review items 1, 4 and 5 in §4. This document
describes the control; it does not certify it.*
