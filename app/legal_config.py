"""
Central legal/compliance configuration — single source of truth (LSAI-LEGAL-01 / 09).

Product identity and the permanently-disabled prohibited-feature flags live here. The prohibited
flags are READ-ONLY guardrails: flipping any to True requires a Founder + qualified-counsel
constitutional amendment (see docs/legal/PROHIBITED_FEATURES.md). Code and tests assert they
stay False. This file does NOT certify legal compliance — it encodes guardrails for human review.
"""

# ── Product identity (LSAI-LEGAL-01) ─────────────────────────────────────────────
APP_POSITIONING = (
    "Source-grounded legal practice operating system for Indian advocates and law firms"
)

# What the product IS NOT (hard identity gates — must stay False):
PUBLIC_AI_LAWYER   = False   # no public/citizen legal-advice mode
LAWYER_MARKETPLACE = False   # no lawyer listing/ranking/marketplace
LEAD_GENERATION    = False   # no client lead selling/generation
ADVOCATE_ADVERTISING = False  # no advocate advertising/solicitation (BCI Rule 36)

# Public-facing disclaimers (rendered in onboarding / assistant / drafting / exports):
DISCLAIMERS = {
    "advocate_only": "For advocates and law firms only — not a public legal-advice service.",
    "ai_review": "AI output is a draft/support tool. A qualified advocate must review it before use.",
    "no_outcome": "No legal outcome is promised or guaranteed.",
    "no_training": "Client and matter data is never used to train AI models, and is never shared across firms.",
}

# ── Prohibited AI features (LSAI-LEGAL-09) ───────────────────────────────────────
# Permanently disabled per CLAUDE.md §1 and the SC draft AI-in-Courts Regs 2026 (reg. 20(d)/(f)).
PROHIBITED_FEATURES = {
    "case_prediction": False,
    "win_probability": False,
    "bail_risk_score": False,
    "recidivism_risk": False,
    "witness_credibility_score": False,
    "judge_behavior_prediction": False,
    "automated_filing": False,
    "ai_evidence_authenticity": False,
    "legal_outcome_guarantee": False,
}


def assert_prohibited_disabled() -> None:
    """Raise if any prohibited feature was switched on. Called at app startup."""
    enabled = [k for k, v in PROHIBITED_FEATURES.items() if v]
    if enabled:
        raise RuntimeError(
            f"PROHIBITED features are enabled: {enabled}. These are barred (CLAUDE.md §1 / "
            f"SC AI-Regs reg.20). Disable them or obtain a Founder+counsel amendment."
        )


# ── Human sign-off gates + pre-publish lock (LSAI-LEGAL-21 / 22) ─────────────────
# These are HUMAN gates and are never self-certified by code. They stay False here; only a
# Founder + the named human reviewer may record approval (via a controlled amendment). The
# public-launch lock is fail-closed: launch stays blocked until every gate is approved.
LAUNCH_GATES = {
    "G1_corpus_authenticity": False,     # senior advocate: sources are authentic/verbatim
    "G6_privacy_review": False,          # DPDP/privacy reviewer
    "G7_security_review": False,         # security reviewer
    "G8_senior_advocate_signoff": False, # senior advocate: AI behaviour + templates
    "closed_beta_validated": False,      # advocates use it without hand-holding
    "willingness_to_pay": False,         # founder/market signal
}


def public_launch_status() -> dict:
    """Report the launch gates and whether public launch is blocked. Fail-closed: blocked unless
    EVERY gate is human-approved. No real client data / public launch until this clears (G6/G7)."""
    pending = [k for k, v in LAUNCH_GATES.items() if not v]
    return {"gates": LAUNCH_GATES, "pending": pending, "blocked": bool(pending)}


def public_launch_blocked() -> bool:
    return public_launch_status()["blocked"]


def identity_summary() -> dict:
    return {
        "positioning": APP_POSITIONING,
        "public_ai_lawyer": PUBLIC_AI_LAWYER,
        "lawyer_marketplace": LAWYER_MARKETPLACE,
        "lead_generation": LEAD_GENERATION,
        "advocate_advertising": ADVOCATE_ADVERTISING,
        "prohibited_features": PROHIBITED_FEATURES,
        "disclaimers": DISCLAIMERS,
    }
