---
name: loop
description: The "Loop" — the standing recovery protocol for LegalServer.AI when you hit a knowledge or capability gap (stuck, blocked, unfamiliar tech, a tool/path that doesn't work). Use whenever you're stuck or about to guess. Acquire the missing knowledge (including online research), capture it as a detailed skill, inform the Master Agent of the skill + its usage, then resume the work under the Latest Master Agent. Founder-mandated 2026-06-22.
---

# The Loop — never guess; learn, capture, continue

Founder directive (2026-06-22): *"whenever stuck follow it … acquire the knowledge by doing
detailed research online as well … write detailed skills … inform Master Agent about skills and
its detailed usage instructions. Now complete all future work with the Latest Master Agent only."*

All work runs under the **Latest Master Agent = V3 Constitution**
(`docs/governance/LEGALSERVERAI_MASTER_AGENT_V3_FIROZ_BRAIN_2026-06-21.md`). The Loop is how the
Master Agent grows: every gap it hits becomes permanent, reusable capability.

## When to enter the Loop
- You're blocked, or unsure, or about to guess at a fact, API, command, or config.
- A tool/path failed and you don't yet know why.
- The task needs knowledge that isn't already in the repo, the skills, or memory.

## The five steps (do them in order)
1. **Name the gap.** State in one line exactly what you don't know or can't yet do.
2. **Acquire the knowledge — for real.**
   - Diagnose empirically (probe, isolate, reproduce). Prefer evidence over assumption.
   - **Research online** (`WebSearch`/`WebFetch`) when the answer isn't in the repo; prefer
     authoritative sources (official docs, AWS/library docs). Cite sources in your report.
   - **Verify** the knowledge by making it actually work before you trust it.
3. **Write it down as a detailed skill.** Expand the relevant `docs/governance/skills/LSAI-SKILL-*`
   (or add one) into a *battle-tested runbook*: exact steps, commands, gotchas you hit, caveats,
   evidence, and honest "not yet done". No theoretical fluff, no invented maturity — only what you
   verified. Mark maturity (SEED→…→DETERMINISTIC) per the V3 ladder.
4. **Inform the Master Agent + record usage.** Update `docs/governance/README.md` / `INDEX.md` to
   point at the new/expanded skill and *when to use it*; add/update a memory entry; update
   `docs/STATUS.md` (+ Desktop mirror) and `project-current-status`. The next session must find it.
5. **Resume under the Master Agent.** Return to the blocked work and finish it using the now-captured
   skill, staying inside the V3 doctrine and the `legal-sprint` loop.

## Hard rules while looping
- Never fabricate a fact, citation, statute, command, or "it works" — if unverified, say so.
- Never put secrets (DB passwords, keys) in chat or git; redact in any output.
- Never self-certify human gates (G1 corpus authenticity, G6/G7 privacy/security, G8 advocate).
- Stop-the-line conditions still apply (cross-tenant leak, uncited answer, unapproved final draft).

## Done when
The gap is closed *and* captured: the work continues, a detailed skill exists, and the Master
Agent's docs/memory point to it so the same gap never costs time twice.
