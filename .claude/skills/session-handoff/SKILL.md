---
name: session-handoff
description: Close out a LegalServer.AI work session so the next one resumes exactly where this left off. Use when the user says "wrap up", "close the session", "update the master agent", "save progress", "we're nearly out of tokens/context", or when a long session is winding down. Writes the status + audit snapshot to STATUS.md and memory.
---

# Session Handoff — make the next session resume exactly here

There is **no automatic token-exhaustion trigger** — so resumability is achieved by leaving
always-current artifacts. Run this whenever a session is winding down, feels long, or the user
asks to save/close. It is safe to run repeatedly (idempotent).

## Do these, in order

### 1. Reconcile the truth
- Run the full test suite: `python -m pytest -q`. Record the real pass count.
- Note anything half-done, any failing/skipped test, any stop-the-line condition.
- Confirm the server still boots (`/health`) if backend changed.

### 2. Update `docs/STATUS.md`
- Header: `Last updated`, `Tests passing` (real count), `Current phase`, **`Next action`**
  (the precise resume point — name the exact file/item to start with).
- Tick completed checkboxes; leave unfinished work clearly marked `🔴/🟡` with what remains.
- Append a dated **session-log** entry at the top of the log:
  files changed · tests (new vs previous) · evidence · gates touched · known gaps · next step.

### 3. Update memory (persists across sessions)
- Update `project-current-status` memory: phase, test count, exact `Next action`, blockers.
- If a durable preference/decision emerged, capture it (feedback/project) and link it.
- Keep `MEMORY.md` index lines accurate.

### 4. Refresh the Living Status block in the Constitution
- Update the "Living Status Addendum" at the end of `LegalServerAI_Master_Agent_Final.md`
  (machine-maintained per Founder instruction) with: date, phase, test count, last item shipped,
  next action, open human gates. Do **not** edit the Articles (only the Founder amends those).

### 5. Produce the close-out report to the user
A short audit snapshot: what shipped this session (with evidence) · current phase & test count ·
open gates/blockers (esp. anything needing the Founder or Senior Advocate) · the exact
`Next action` the next session will start from.

## Resume contract
Next session: invoke `master-agent` (or just read Constitution → CLAUDE.md → STATUS.md), then
start from STATUS.md `Next action`. Nothing should need re-discovery.
