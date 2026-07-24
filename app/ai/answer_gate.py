"""Fail-closed answer gate: repair-or-withhold, not warn (Phase 2).

WHY THIS EXISTS
---------------
`safety.enforce_citations` calls itself a "hard-gate" but appends a warning and returns
the answer. An answer citing a provision absent from the retrieved sources still reached
the advocate; the only defence was a notice below it, which a hurried reader scrolls past.
Streaming made it worse — the fabricated citation was already on screen before any check
ran, so the warning arrived after the damage.

For a tool whose output goes into filings, a fabricated section is the worst failure mode
available. So the gate now DECIDES, and the decision is one of three:

    ok        — every citation resolves against the approved context; show it
    repaired  — the sentences carrying unverified citations were REMOVED; show the rest,
                labelled, so the advocate gets the sound part of the answer
    withheld  — what remained after repair could not stand on its own; show a refusal
                instead of the answer

This is deliberately conservative: it removes content rather than trusting it. The cost of
withholding a good answer is an advocate who has to ask again. The cost of showing a bad
citation is a filing with a provision that does not exist.

NOTE ON SCOPE: this validates CITATIONS against retrieved context. It does not verify that
the answer's legal reasoning follows from the sources — claim-to-source entailment is a
separate, harder problem (see docs/AUDIT_CLAIM_VERIFICATION_2026-07-24.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ai.safety import unverified_citations

# Sentence split. Breaks after . ! ? followed by whitespace + a capital/quote/bullet.
# The negative lookbehind keeps "Sec." / "No." / "v." / a bare "Section 138." from
# splitting mid-citation, which would strand a citation in its own fragment and make the
# repair either too aggressive or too timid.
_ABBREV = r"(?<!\bSec)(?<!\bsec)(?<!\bNo)(?<!\bno)(?<!\bv)(?<!\bVs)(?<!\bvs)(?<!\bArt)(?<!\bart)"
_SENTENCE_SPLIT = re.compile(rf"{_ABBREV}(?<=[.!?])\s+(?=[\"'“'(\[•\-\d]?[A-Z])")

WITHHELD_MESSAGE = (
    "I could not give you an answer I can stand behind on this one.\n\n"
    "The response I generated cited provisions that do not appear in the sources I "
    "retrieved, and after removing them there was not enough verified material left to "
    "be useful. Rather than show you legal content I cannot ground in a source, I am "
    "withholding it.\n\n"
    "Try naming the act and section directly (e.g. \"Section 138 of the Negotiable "
    "Instruments Act\"), which routes to an exact lookup instead of a semantic search."
)

# The notice names what was dropped — an advocate is entitled to know, and may want to
# check it themselves. It is worded so it can NEVER be read as a statement of law: the
# provision is described as not found, with an explicit warning that it may not exist.
# Everything after NOTICE_MARK is commentary about the answer, never part of the answer.
NOTICE_MARK = "\n\n---\n"
REPAIRED_NOTICE = (
    NOTICE_MARK
    + "⚠ **Part of this answer was removed before you saw it.** It relied on {cites}, "
    "which could not be found in the retrieved sources. Those passages were withheld "
    "rather than shown to you. **Treat the reference as unverified — it may be "
    "misnumbered or may not exist at all.** What remains is grounded in the sources listed "
    "below."
)


@dataclass
class AnswerVerdict:
    """The gate's decision. `text` is the ONLY thing that may be shown to the advocate."""
    status: str                              # "ok" | "repaired" | "withheld"
    text: str
    unverified: list[str] = field(default_factory=list)
    removed_sentences: list[str] = field(default_factory=list)
    reason: str | None = None

    @property
    def blocked(self) -> bool:
        return self.status != "ok"

    @property
    def body(self) -> str:
        """The answer itself, without the gate's own commentary.

        The safety property is about THIS: a citation the gate rejected must never appear
        in the body. It may appear in the notice below the separator, where it is framed
        as unverified and explicitly not relied upon.
        """
        return self.text.split(NOTICE_MARK, 1)[0]

    def to_event(self) -> dict:
        """Compact, non-sensitive summary for the SSE stream / logs."""
        return {
            "status": self.status,
            "unverified": self.unverified,
            "removed_count": len(self.removed_sentences),
            "reason": self.reason,
        }


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _has_substance(text: str) -> bool:
    """Is what survived repair worth showing?

    Requires real prose, not a stub like "Yes." left behind after the substantive
    sentences were removed — a fragment reads as a confident answer while carrying none
    of the reasoning the advocate needed.
    """
    stripped = text.strip()
    return len(stripped) >= 120 and len(split_sentences(stripped)) >= 2


def validate_answer(answer: str, approved_context: str) -> AnswerVerdict:
    """Decide whether `answer` may be shown, repaired, or must be withheld.

    `approved_context` is the retrieved, source-verified material — the ONLY thing a
    citation may be grounded in. Empty context means nothing is verifiable, so any
    citation at all is unverified (that is `unverified_citations`' existing behaviour and
    the correct fail-closed reading).
    """
    if not answer or not answer.strip():
        return AnswerVerdict(status="ok", text=answer)

    bad = unverified_citations(answer, approved_context)
    if not bad:
        return AnswerVerdict(status="ok", text=answer)

    bad_set = {b.upper() for b in bad}
    kept, removed = [], []
    for sentence in split_sentences(answer):
        # A sentence is removed if it cites any unverified provision.
        if unverified_citations(sentence, approved_context) and _cites_any(sentence, bad_set):
            removed.append(sentence)
        else:
            kept.append(sentence)

    repaired = " ".join(kept).strip()

    if not removed:
        # Citation present but not attributable to a sentence (e.g. inside a table or
        # heading the splitter did not isolate). Cannot repair surgically → withhold.
        return AnswerVerdict(
            status="withheld", text=WITHHELD_MESSAGE, unverified=bad,
            reason="unverified citation could not be isolated for removal")

    if not _has_substance(repaired):
        return AnswerVerdict(
            status="withheld", text=WITHHELD_MESSAGE, unverified=bad,
            removed_sentences=removed,
            reason="too little verified content remained after removal")

    notice = REPAIRED_NOTICE.format(cites=", ".join(f"Section {b}" for b in bad))
    return AnswerVerdict(
        status="repaired", text=repaired + notice, unverified=bad,
        removed_sentences=removed,
        reason="removed passages citing unverified provisions")


def _cites_any(sentence: str, wanted: set[str]) -> bool:
    from app.ai.safety import extract_citations
    return bool(extract_citations(sentence) & wanted)
