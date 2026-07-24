"""Deterministic citation-resolution guard (Phase 4).

Post-generation check: every statutory citation an answer DISPLAYS must resolve to a real section
in the source-verified corpus. A citation to a section that does not exist in the named act is a
**fabricated citation** — the answer must be repaired or refused, never shown to an advocate.

This is the deterministic half of the citation gate (the release threshold "100% of displayed
citations resolve to stored source records"). It does NOT judge whether the cited provision actually
*supports* the proposition — claim-to-span ENTAILMENT needs NLI / senior-advocate review and is
tracked as a separate gate (see docs/HUMAN_GATE_EVIDENCE.md).
"""
import re

from app.ai.rag import _ACT_ALIASES, _SECTION_RE


def _act_mentions(text_lc: str) -> list[tuple[int, int, str]]:
    """(position, alias_length, act_title) for every act-alias occurrence. alias_length lets the
    pairing prefer the most-specific alias (longest-wins), so "Income-tax Act 2025" isn't matched
    by the shorter bare "income tax" (which maps to the 1961 Act)."""
    out: list[tuple[int, int, str]] = []
    for aliases, title in _ACT_ALIASES:
        for a in aliases:
            for m in re.finditer(re.escape(a), text_lc):
                out.append((m.start(), len(a), title))
    return out


def _resolve(collection, act_title: str, sec: str, kind: str) -> bool:
    """True if (act, section) exists in the corpus. Mirrors retrieve_by_section's intent order
    (article -> Schedule namespace first) so a real Schedule article isn't judged fabricated."""
    base = sec.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    candidates = (f"Sch.{sec}", sec, base) if kind == "article" else (sec, base, f"Sch.{sec}")
    for sval in candidates:
        try:
            got = collection.get(
                where={"$and": [{"act_title": act_title}, {"section": sval}]}, limit=1)
        except Exception:
            got = {"ids": []}
        if got.get("ids"):
            return True
    return False


def verify_citations(text: str, collection=None) -> dict:
    """Resolve every statutory citation in ``text`` against the corpus.

    Returns a report with ``resolved`` / ``unresolved`` (fabricated: act named but the section does
    not exist) / ``unverifiable`` (a number with no nearby act to check against), and
    ``all_resolved`` (no fabricated citations). ``collection`` is injectable for tests.
    """
    if collection is None:
        from app.ai.vector_store import get_collection
        collection = get_collection()

    acts = _act_mentions(text.lower())

    citations: list[dict] = []
    for m in _SECTION_RE.finditer(text):
        kind = "article" if m.group(1).lower().startswith("art") else "section"
        num = m.group(2).replace(" ", "").upper()
        pos = m.start(2)
        # Prefer an act named right AFTER the number ("Section N of the ACT", within 80 chars);
        # else the nearest act mentioned before it (within 120 chars). Ties break to the LONGEST
        # (most specific) alias so "... of the Income-tax Act 2025" attributes to the 2025 Act.
        after = [(s - pos, -alen, t) for (s, alen, t) in acts if 0 <= s - pos <= 80]
        before = [(pos - s, -alen, t) for (s, alen, t) in acts if 0 <= pos - s <= 120]
        act = min(after)[2] if after else (min(before)[2] if before else None)
        citations.append({"kind": kind, "section": num, "act": act})

    resolved, unresolved, unverifiable = [], [], []
    for c in citations:
        if not c["act"]:
            unverifiable.append(c)
        elif _resolve(collection, c["act"], c["section"], c["kind"]):
            resolved.append(c)
        else:
            unresolved.append(c)

    return {
        "citations": citations,
        "resolved": resolved,
        "unresolved": unresolved,
        "unverifiable": unverifiable,
        "all_resolved": len(unresolved) == 0,
    }


def integrity_event(answer: str, collection=None) -> dict | None:
    """Non-blocking corpus-integrity signal for the answer path. Returns a payload naming any
    HARD-fabricated citations (act-qualified section absent from the corpus), or ``None`` if the
    answer is clean. The caller logs it + may surface it to the UI; it never blocks the answer."""
    vc = verify_citations(answer, collection=collection)
    if vc["all_resolved"]:
        return None
    return {"ok": False,
            "fabricated": [f"{c['act']} — Section {c['section']}" for c in vc["unresolved"]]}
