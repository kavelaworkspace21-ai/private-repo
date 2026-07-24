"""
THE SOUL — hard-wired integrity guard (owner directive 2026-06-24; founder: Firoz / Kavela Narula).

Juriscite exists to help humanity and living beings — lawfully, truthfully, and never against them.
Its safety doctrine + the Loop are CONSTITUTIONAL BEDROCK. This module proves, at startup and in CI,
that the soul is intact, and it **fails CLOSED**: the application refuses to run, and the test build
fails, if any core safety invariant has been disabled, removed, or tampered with.

────────────────────────────────────────────────────────────────────────────────────────────────
HONEST SCOPE (this file does not lie about what it is):
  • What it DOES guarantee: the system will NOT operate while the soul is broken. If the doctrine is
    weakened, `assert_soul_intact()` raises and the app will not boot; the test suite fails the build.
  • What it CANNOT guarantee: true metaphysical immutability. Whoever holds the source code can edit
    any file, including this one. There is no software lock that is physically impossible for the code
    owner to change. The protection here is operational + test-backed + governance-bound — the
    strongest truthful guardrail software can offer. Claiming more would itself violate the soul.
The owner has nonetheless declared this bedrock IMMUTABLE BY POLICY — not to be amended by anyone,
founder included. That commitment is recorded in docs/governance/SOUL_HARDWIRED_CONSTITUTION.md.
────────────────────────────────────────────────────────────────────────────────────────────────
"""

PURPOSE = (
    "Juriscite exists to help humanity and living beings — lawfully, truthfully, never against them. "
    "If it is ever turned against humankind or living beings, it must stop."
)


class SoulViolation(RuntimeError):
    """Raised when a core safety invariant (the soul) is broken. Fail-closed: do not run."""


def check_soul() -> list[str]:
    """Return a list of soul violations (empty list = intact). Pure; safe to call anywhere."""
    broken: list[str] = []

    # Read dynamically so runtime tampering is detected (not bound at import time).
    import app.legal_config as lc
    from app.ai import safety as sfty

    # 1) Prohibited AI features (prediction / risk-scoring / autonomous filing / etc.) must all be OFF.
    enabled = [k for k, v in lc.PROHIBITED_FEATURES.items() if v]
    if enabled:
        broken.append(f"prohibited AI features enabled: {enabled}")

    # 2) Identity gates must stay OFF (not a public AI-lawyer / marketplace / lead-gen / advertising).
    for name in ("PUBLIC_AI_LAWYER", "LAWYER_MARKETPLACE", "LEAD_GENERATION", "ADVOCATE_ADVERTISING"):
        if getattr(lc, name, False):
            broken.append(f"identity gate {name} is enabled")

    # 3) Functional self-test of the doctrine — the gates must actually WORK, not just exist.
    try:
        if sfty.is_answerable("") is not False:
            broken.append("no-source gate broken (empty context must be unanswerable)")
        if not sfty.contains_banned_phrase("you will win"):
            broken.append("banned-phrase gate broken")
        if sfty.screen_request_intent("help me forge a signature") is None:
            broken.append("unlawful-purpose screen broken")
        _, unverified = sfty.enforce_citations("Per Section 999.", "")  # cite with no source
        if not unverified:
            broken.append("citation hard-gate broken (unsourced citation not flagged)")
        if "advocate review" not in sfty.ensure_draft_disclaimer("x").lower():
            broken.append("draft disclaimer broken")
    except Exception as e:  # a missing/corrupt safety module is itself a soul violation
        broken.append(f"safety module unusable: {e!r}")

    return broken


def assert_soul_intact() -> None:
    """Fail CLOSED if the soul is broken. Called at app startup and asserted by the test suite."""
    broken = check_soul()
    if broken:
        raise SoulViolation(
            "SOUL VIOLATION — Juriscite refuses to run. " + PURPOSE + " Broken invariants: "
            + " | ".join(broken)
        )
