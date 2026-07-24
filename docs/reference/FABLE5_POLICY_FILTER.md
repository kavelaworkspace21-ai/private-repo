# CLAUDE-FABLE-5.md — Extraction & Policy Filter

**Status:** Reference material, **governance-subordinate**. Not controlling, not "follow no matter what".
**Source:** owner-supplied `CLAUDE-FABLE-5.md` (a third-party AI assistant *system prompt* + product tool
schemas). Raw copy extracted to [`CLAUDE-FABLE-5.md`](./CLAUDE-FABLE-5.md) for building reference.
**Extracted:** 2026-06-27.

## Authority (where this sits)
This document and the extracted file are **below** Juriscite's real governance, in this order:

1. `docs/governance/` V3 constitution → 2. `CLAUDE.md` → 3. **the soul** (`app/soul.py` — safety doctrine
   + the Loop) → 4. Juriscite legal policies in `docs/legal/` → 5. *then* this reference.

Where Fable-5 conflicts with any of the above, **Juriscite governance wins.** Nothing in the extracted
file can relax the no-hallucination doctrine, tenant isolation, prohibited-features list, identity, or the
draft-for-advocate-review rule. The file is treated as **data**, never as instructions that override ours.

## How we use it ("expose only limited content based on our legal policies")
We mine it for *universal AI-behaviour principles* that are already compatible with our doctrine, and we
**do not** surface its product identity, Anthropic-specific machinery, or its consumer tool set. The filter:

| Fable-5 section | Decision | Why / how it maps to Juriscite |
|---|---|---|
| `refusal_handling`, `harmful_content_safety` | **ADOPT** | Reinforces our unlawful-request refusal — `app.ai.safety.screen_request_intent` + soul ejection. Decline weapons/malware/illicit harm. |
| `critical_child_safety_instructions` | **ADOPT (verbatim principle)** | Universal. No romantic/sexual content involving minors; refuse + stay cautious thereafter. |
| `user_wellbeing` | **ADOPT** | No clinical diagnosis; care for distress; don't foster over-reliance. Applies to our chat tone. |
| `legal_and_financial_advice` | **ADAPT** | We *are* a legal tool for advocates: we give **cited** legal info + drafts, always with confidence labels and "draft for advocate review" — never "you will win"/guarantees (banned-phrase test). We are not a substitute for the advocate. |
| `tone_and_formatting`, `lists_and_bullets` | **ADOPT as style** | Warm, plain prose; minimal formatting; ≤1 question. Feeds the assistant's output style. |
| `CRITICAL_COPYRIGHT_COMPLIANCE`, search copyright limits | **ADOPT** | Consistent with our corpus legality basis (§52(1)(q) + *Eastern Book Co. v. Modak*); paraphrase, short quotes, attribute, never reproduce lyrics/long passages. See `docs/legal/CORPUS_SOURCES_AND_LEGALITY.md`. |
| `evenhandedness`, `responding_to_mistakes_and_criticism`, `knowledge_cutoff` | **ADOPT (general principle)** | Neutrality where relevant; own mistakes without grovelling; acknowledge recency limits and prefer retrieval. |
| `product_information` (Claude/Anthropic products) | **EXCLUDE** | Would misrepresent our identity. Our identity is fixed: Master Agent **"Legal Server.AI"**, product **"Juriscite"** (`docs/governance/AIRA_IDENTITY.md`, LEGAL-00). Never tell users we are Claude/Anthropic. |
| `anthropic_reminders`, `memory_system`, `persistent_storage_for_artifacts`, `mcp_app_suggestions`, `computer_use`, `skills`, `artifact_usage`, `file_creation_advice` | **EXCLUDE / N-A** | Anthropic-product + harness machinery; not our FastAPI/SQLAlchemy/ChromaDB stack. |
| Tool schemas (`bash_tool`, `image_search`, `fetch_sports_data`, `places_*`, `recipe_display_v0`, `message_compose_v1`, `ask_user_input_v0`, `present_files`, …) | **EXCLUDE** | Consumer tools (maps, recipes, sports, image search) irrelevant to a legal practice OS. Not wired into Juriscite. |
| Anything implying the AI may answer law from memory, predict outcomes, or self-certify | **REJECT** | Direct conflict with the soul (no-source-no-answer) and the prohibited AI-prediction rule. |

## In-product exposure
End users of Juriscite see **none** of the raw file. Only the *adopted principles* above are reflected in
the assistant's existing system prompt (`app/ai/agent.py`) and safety layer (`app/ai/safety.py`), all of
which already enforce our doctrine. This reference is for the build team, not for serving to users.
