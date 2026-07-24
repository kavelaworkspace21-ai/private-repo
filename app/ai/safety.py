"""
Safety doctrine enforcement (CLAUDE.md section 2 — "the heart of this product").

Pure, dependency-free helpers so they are trivially unit-testable:
  • Confidence labelling      (HIGH / MEDIUM / LOW)
  • Banned-phrase detection   (section 2.6)
  • Mandatory draft disclaimer (section 2.7)
  • Draft status constant      (section 2.4)
  • "No source, no answer" gate (section 2.1)
"""
import re
from enum import Enum

# ── Draft status (section 2.4) ──────────────────────────────────────────────────
DRAFT_STATUS_REVIEW = "DRAFT_FOR_ADVOCATE_REVIEW"
DRAFT_STATUS_APPROVED = "ADVOCATE_APPROVED"

# ── Mandatory disclaimer that ends every draft (section 2.7) ─────────────────────
DRAFT_DISCLAIMER = (
    "Draft for advocate review. Verify facts, jurisdiction, limitation, court rules, "
    "and latest case law before filing."
)

# AI-generated-content disclosure — aligns with the draft Supreme Court "Regulations for
# Use of AI in Courts, 2026" (reg. 7 transparency; reg. 20(h): AI-generated output must not
# be submitted to a court without full disclosure of its AI-generated character).
AI_GENERATED_NOTICE = (
    "AI-assisted content. If this document is filed in or submitted to a court, its "
    "AI-generated character must be disclosed."
)


# ── Confidence labelling (section 2.5) ──────────────────────────────────────────
class Confidence(str, Enum):
    HIGH = "HIGH"      # direct verified section/source match
    MEDIUM = "MEDIUM"  # source-backed, needs interpretation
    LOW = "LOW"        # unclear / no source — advocate review required


def assess_confidence(has_verified_text: bool, has_any_source: bool) -> Confidence:
    """
    HIGH   — at least one VERIFIED verbatim statutory/case source was retrieved.
    MEDIUM — sources retrieved, but only heading-level (needs interpretation).
    LOW    — nothing retrieved; the agent must refuse/escalate.
    """
    if has_verified_text:
        return Confidence.HIGH
    if has_any_source:
        return Confidence.MEDIUM
    return Confidence.LOW


# ── Banned phrases (section 2.6) ────────────────────────────────────────────────
# Outcome-guaranteeing / lawyer-replacing / urgency language the AI must never emit.
BANNED_PATTERNS = [
    r"you will win",
    r"you'?ll win",
    r"\bguarantee(d|s)?\b",
    r"this is guaranteed",
    r"file this immediately",
    r"replaces? a lawyer",
    r"no need for a lawyer",
    r"the court will definitely",
    r"will definitely win",
    r"100%\s*(sure|certain|guaranteed)",
    r"certain to succeed",
    r"sure shot",
]
_BANNED_RE = [re.compile(p, re.IGNORECASE) for p in BANNED_PATTERNS]


def find_banned_phrases(text: str) -> list[str]:
    """Return the list of banned phrases found in the text (empty = clean)."""
    if not text:
        return []
    hits = []
    for rx in _BANNED_RE:
        m = rx.search(text)
        if m:
            hits.append(m.group(0))
    return hits


def contains_banned_phrase(text: str) -> bool:
    return bool(find_banned_phrases(text))


def sanitize_answer(text: str) -> str:
    """
    Last-resort guard: redact any banned phrase that slipped through so it can never
    reach an advocate verbatim. Replaced with a neutral marker.
    """
    if not text:
        return text
    out = text
    for rx in _BANNED_RE:
        out = rx.sub("[removed: non-compliant claim]", out)
    return out


# ── No source, no answer (section 2.1) ──────────────────────────────────────────
def is_answerable(retrieved_context: str) -> bool:
    """True only if real sources were retrieved. Empty context => must refuse."""
    return bool(retrieved_context and retrieved_context.strip())


REFUSAL_MESSAGE = (
    "I could not find this in my verified legal sources, so I will not answer from "
    "memory. Please confirm the provision at indiacode.nic.in, or narrow the question "
    "to a specific Act and section so I can retrieve the exact text."
)


# ── Unlawful-purpose input screen (LSAI-LEGAL-08) ───────────────────────────────
# Narrow, intent-framed patterns: the user is asking the AI to HELP commit a wrong against
# the justice process (forging/fabricating evidence, bribery, intimidation, knowingly false
# filings, impersonation). Deliberately requires help/how-to framing so it does NOT block
# legitimate legal questions ABOUT these offences (e.g. "what is the punishment for forgery").
UNLAWFUL_INTENT_PATTERNS = [
    r"\b(help|show|teach|tell)\s+me\s+(how\s+)?(to\s+)?(forge|fabricate|fake|falsify|bribe|intimidate)\b",
    r"\bhow\s+(do|can|to)\s+i?\s*(forge|fabricate|falsify|bribe|intimidate)\b",
    r"\bfabricat\w*\s+(evidence|document|documents|proof|witness)\b",
    r"\bforge\s+(a\s+|an\s+|the\s+)?(signature|document|stamp|order|judgment|judgement|seal)\b",
    r"\bbribe\s+(a\s+|an\s+|the\s+)?(judge|magistrate|officer|official|clerk|witness|cop|police)\b",
    r"\b(threaten|intimidate|silence)\s+(a\s+|an\s+|the\s+)?(witness|judge|complainant|victim|juror)\b",
    r"\b(file|draft|register)\s+(a\s+|an\s+)?(false|fake|bogus|fabricated)\s+(complaint|fir|case|affidavit)\b",
    r"\bfake\s+stamp\s+paper\b",
    r"\bdestroy\s+(the\s+)?evidence\b",
    r"\bplant\s+(the\s+)?evidence\b",
    r"\bimpersonat\w*\s+(a\s+|an\s+|the\s+)?(advocate|lawyer|officer|official|judge)\b",
]
_UNLAWFUL_RE = [re.compile(p, re.IGNORECASE) for p in UNLAWFUL_INTENT_PATTERNS]

UNLAWFUL_REFUSAL = (
    "I can't help with that. This request appears to seek help to do something unlawful — "
    "such as fabricating or forging evidence/documents, bribery, intimidating a participant in "
    "legal proceedings, or making a knowingly false filing. I can help with lawful legal "
    "research, court procedure, and drafting for an advocate's review."
)


def screen_request_intent(text: str) -> str | None:
    """Return a refusal message if the user is asking for help to commit a clear wrong against
    the justice process; otherwise None. Narrow by design (requires help/how-to framing)."""
    if not text:
        return None
    for rx in _UNLAWFUL_RE:
        if rx.search(text):
            return UNLAWFUL_REFUSAL
    return None


# ── Citation hard-gate (section 2.2) ────────────────────────────────────────────
# Matches statutory citations like "Section 318", "s. 138", "§ 304A", "Article 21".
_CITATION_RE = re.compile(
    r"\b(?:section|sections|sec\.?|s\.|§|article|articles|art\.)\s*"
    r"(\d{1,4}[A-Z]{0,2})",
    re.IGNORECASE,
)


def extract_citations(text: str) -> set[str]:
    """Return the set of cited section/article numbers (normalised, e.g. {'318','304A'})."""
    if not text:
        return set()
    return {m.group(1).upper() for m in _CITATION_RE.finditer(text)}


def unverified_citations(answer: str, retrieved_context: str) -> list[str]:
    """
    Section/article numbers the answer cites that are NOT present in the retrieved
    sources. A non-empty result means the answer is making an UNVERIFIED legal claim.
    With no retrieved context at all, every citation is unverified.
    """
    cited = extract_citations(answer)
    if not cited:
        return []
    available = extract_citations(retrieved_context) if retrieved_context else set()
    return sorted(cited - available)


CITATION_GATE_NOTICE = (
    "CITATION CHECK — the following citation(s) could not be verified against the "
    "retrieved sources and may be inaccurate. Do NOT rely on them without confirming "
    "the official text at indiacode.nic.in: "
)


def enforce_citations(answer: str, retrieved_context: str) -> tuple[str, list[str]]:
    """
    Hard-gate: if the answer cites a provision not in the retrieved sources, append a
    prominent verification warning so an unverified legal claim can never reach the
    advocate unflagged. Returns (gated_answer, unverified_list).
    """
    bad = unverified_citations(answer, retrieved_context)
    if not bad:
        return answer, []
    notice = ("\n\n---\n⚠ " + CITATION_GATE_NOTICE
              + ", ".join(f"Section {b}" for b in bad) + ".")
    return answer.rstrip() + notice, bad


# ── Draft finalisation (section 2.7) ────────────────────────────────────────────
def ensure_draft_disclaimer(text: str) -> str:
    """Append the mandatory disclaimer if not already present."""
    if not text:
        return DRAFT_DISCLAIMER
    if DRAFT_DISCLAIMER.split(".")[0].lower() in text.lower():
        return text
    return text.rstrip() + "\n\n---\n" + DRAFT_DISCLAIMER
