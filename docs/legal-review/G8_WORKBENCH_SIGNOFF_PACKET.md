# Gate G8 — Advocate Workbench Sign-off Packet

**Status: READY FOR REVIEW — UNSIGNED.**
Prepared by the build agent on 2026-07-11 (LSAI-WB-09). Per the constitution and pack §7, this
gate is **human-only**: the build agent does not and cannot certify it. Beta advocates should
not rely on Workbench outputs until a senior advocate signs below.

---

## 1. What you are signing off

The six Workbench workflows' **prompt contracts and behaviour** — that their intake questions,
section schemas, and safety conduct are professionally sound for use by practising advocates
(assisted, always subject to per-output advocate review).

## 2. What to review (all prompts-as-data — no code reading required)

| Item | Where |
|---|---|
| The 6 workflow schemas: intake questions + exact section lists | `app/services/workbench/workflows.py` (readable top-to-bottom) |
| The generation rules injected around every schema | `app/services/workbench/engine.py::_llm_generate` (the numbered ABSOLUTE RULES block) + `ai/prompts/workbench/README.md` |
| Draft skeletons the Drafting Engine formats against (28) | `templates/drafts/` + `manifest.json` (also G8-pending) |

## 3. How to produce sample outputs for review
Sign in as a test advocate → **Workbench** → run each tool once with a realistic matter
(the packet reviewer's own anonymised facts work best). Every artifact can be exported to
Word/PDF from the artifact view for margin comments.

## 4. What the machinery already guarantees (so you can focus on professional judgement)
Enforced in code with 449 automated tests (63-case Workbench eval suite at 100%):
- Question-first: nothing generates from an unanswered intake; skipped answers become printed
  "Stated Assumptions".
- No source, no answer: legal sections must cite retrieved verbatim statute or are withheld;
  all-blocked → the artifact refuses.
- Judgments: only live Indian Kanoon results with real links can be referenced; fabricated
  references are stripped visibly; Conflicting Views needs sources on both sides; the good-law
  caveat is guaranteed.
- Quotables (Judgment Analyzer): exact substrings of the source with correct pinpoint page, or
  withheld.
- No outcome prediction, ever: probes are refused before generation; banned phrases are scrubbed.
- Every artifact starts DRAFT_FOR_ADVOCATE_REVIEW; approval is an explicit, audited advocate act.
- Tenant isolation, plan metering, and audit rows throughout.

## 5. Questions for the reviewing advocate
1. Are any intake questions missing/misleading for real practice? (per tool)
2. Are the section schemas complete and correctly ordered for court-ready work product?
3. Is the qualitative strengths/weaknesses language appropriately non-predictive?
4. Are the three hearing-note formats (5-min / 15-min / one-page) usable as-is?
5. Any Bar Council / professional-conduct concern in how outputs are framed or exported?

## 6. Sign-off (human only)

| Field | |
|---|---|
| Reviewing senior advocate | ______________________________ |
| Enrolment no. | ______________________________ |
| Tools reviewed (list) | ______________________________ |
| Changes required before beta | ______________________________ |
| **Approved for closed-beta use** | ☐ YES ☐ NO (date: ____________) |
| Signature | ______________________________ |

*Until signed YES, the Workbench remains builder-verified only. The launch lock (LEGAL-22)
stays engaged regardless of this gate.*
