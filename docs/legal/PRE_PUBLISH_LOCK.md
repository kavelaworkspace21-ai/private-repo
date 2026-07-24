# Pre-Publish Lock (LSAI-LEGAL-22)

**Version:** 0.1 · **Last updated:** 2026-06-23 · **Status: 🔒 LOCKED (public launch blocked)**

A fail-closed lock so the product cannot be publicly launched (or fed real client data) before the
human gates are signed. The lock is enforced in code and asserted by a test.

## Mechanism
- `legal_config.LAUNCH_GATES` — every gate defaults to `False` (G1/G6/G7/G8 + closed-beta + WTP).
- `legal_config.public_launch_blocked()` returns **True** while any gate is unapproved (fail-closed).
- `tests/test_prepublish_lock.py` asserts the lock is engaged by default and that prohibited features
  stay disabled — so the lock can't be removed accidentally.

## To unlock (humans only)
1. Complete `HUMAN_SIGNOFF_PACKET.md` — G1, G6, G7, G8 (+ beta, WTP) signed by the named reviewers.
2. Record approval by flipping the corresponding `LAUNCH_GATES` entries to `True` via a **controlled
   amendment** (Founder + reviewer), in the same commit that updates this doc to UNLOCKED.
3. Only then may public launch / real-client-data onboarding proceed.

## Current state (truthful)
All gates **OPEN**. The app is **feature-complete and deployed for closed testing**, but remains
**locked** for public launch and real client data until G6 + G7 (and G1 + G8 for AI claims) are signed.
This lock is a safeguard, not a legal opinion.
