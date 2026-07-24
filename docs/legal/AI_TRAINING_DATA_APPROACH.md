# Juriscite — AI Data & Anti‑Hallucination Approach

**Version:** 0.1 · **Updated:** 2026-06-25

How Juriscite's AI is made knowledgeable and kept hallucination‑free. **We do NOT fine‑tune a model**
(no GPUs/budget/labelled+advocate‑reviewed corpus, and fine‑tuning *increases* hallucination on legal
facts). Instead we use **RAG + grounding + few‑shot + evaluation** — the design that lets an answer be
*cited and verifiable*, which is what a courtroom needs.

## The four data assets ("datasets") and their categories

### 1. Verified statute corpus (the AI's knowledge)
Verbatim bare‑act text, deterministically extracted (no AI), with provenance (source URL + SHA‑256 +
page). **Categories:** Criminal (BNS/BNSS/BSA, IPC/CrPC/Evidence) · Constitutional · Civil (Contract,
CPC, Specific Relief, Limitation, TP Act) · Family (Hindu Marriage…) · Commercial (Companies, NI Act,
Arbitration, IBC) · Consumer/RTI · Tax (Income‑tax, CGST) · Motor Vehicles · IT/Cyber. **Status:** 19
acts / ~5,047 sections, growing via `fetch_statutes` + `ingest_statutes`.

### 2. Live case‑law (judgments)
Real judgments via the Indian Kanoon API, cited with links; good‑law status flagged unverified. Never
fabricated. **Categories:** Supreme Court + High Court judgments, by topic of the query.

### 3. Few‑shot exemplars (in‑context "teaching" — no fine‑tuning)
Gold examples wired into the agent prompt (`FEW_SHOT_EXEMPLARS`) that demonstrate: cite only from the
retrieved block, confidence labelling, refuse‑when‑no‑source, never invent a section, refuse unlawful
asks. **This is the active anti‑hallucination lever.**

### 4. Legal‑QA evaluation set (measurement)
Graded cases to *measure* and prevent regressions. **Categories:**
- **Answerability** — no source ⇒ must refuse.
- **Citation‑gate** — unsourced citations must be flagged.
- **Banned‑phrase** — outcome/again‑lawyer language must never appear.
- **Unlawful‑intent** — misuse requests must be refused.
- **Knowledge** (future, advocate‑graded) — question → expected cited provision.
Current deterministic set: `app/ai/evals/legal_eval_set.py` (15 cases @ 100%).

## How hallucination is actually prevented (enforced in code + tests)
1. **No source → no answer** (`safety.is_answerable`).
2. **Cite only retrieved provisions; unsourced citations flagged** (`safety.enforce_citations`).
3. **Confidence label** on every answer.
4. **Banned‑phrase block** + **draft disclaimer** + **AI‑generated disclosure**.
5. **Few‑shot exemplars** model the discipline every turn.
6. **Eval suite** fails the build if any guarantee breaks.

## If a real fine‑tune is ever wanted (future, owner‑gated)
It would require: a budget + GPUs, a **senior‑advocate‑labelled** Q→A dataset, a held‑out eval, and
**G8 sign‑off** — and even then it sits *behind* RAG, never replacing source‑grounding. Not done; scoped
honestly when resourced.
