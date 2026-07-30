"""
Legal library access — read-only browse over the ingested corpus.

Source of truth (in priority order):
  1. legal_corpus/fulltext/*.fulltext.json  → verbatim, source-verified statute text
  2. legal_corpus/*.json (law_index etc.)    → heading-only acts not yet full-text

Everything here is public legal data (not tenant-scoped) but still requires login.
Results always expose `source_verified` and a `source_url` so an advocate can verify.
"""
import json
import functools
from pathlib import Path

CORPUS_DIR = Path(__file__).parent.parent / "legal_corpus"
FULLTEXT_DIR = CORPUS_DIR / "fulltext"


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    """Load all acts into {act_id: {meta, sections:[{num,title,text}]}}. Cached."""
    acts: dict[str, dict] = {}

    # Pass 1 — verified full text (preferred)
    if FULLTEXT_DIR.exists():
        for f in sorted(FULLTEXT_DIR.glob("*.fulltext.json")):
            try:
                data = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            for a in data.get("acts", []):
                acts[a["id"]] = {
                    "id": a["id"], "title": a["title"], "short": a.get("short", ""),
                    "year": a.get("year"), "status": a.get("status", "in_force"),
                    "source_verified": True,
                    "source_url": (a.get("source") or {}).get("url", ""),
                    "sections": [
                        {"num": s["num"], "title": s.get("title", ""), "text": s.get("text", "")}
                        for s in a.get("sections", [])
                    ],
                }

    # Pass 2 — heading-only acts (only if not already full-text).
    # Dedupe by NORMALISED TITLE+YEAR, not just id: the old heading index uses different
    # ids than the fulltext registry (e.g. tpa_1882 vs transfer_of_property_1882), which
    # used to double-list acts in the Library once their verbatim text was ingested.
    def _tkey(title: str, year) -> str:
        t = (title or "").lower().replace("the ", " ")
        t = "".join(ch for ch in t if ch.isalnum())
        return f"{t}|{year or ''}"

    verified_keys = {_tkey(a["title"], a["year"]) for a in acts.values()}
    for f in sorted(CORPUS_DIR.glob("*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for a in data.get("acts", []):
            if a["id"] in acts or _tkey(a["title"], a.get("year")) in verified_keys:
                continue
            secs = a.get("sections", a.get("key_sections", []))
            acts[a["id"]] = {
                "id": a["id"], "title": a["title"], "short": a.get("short", ""),
                "year": a.get("year"), "status": a.get("status", "in_force"),
                "source_verified": False, "source_url": "",
                "sections": [
                    {"num": s["num"], "title": s.get("title", ""), "text": s.get("text", "")}
                    for s in secs
                ],
            }
    return acts


def refresh():
    _load.cache_clear()


def list_acts() -> list[dict]:
    out = []
    for a in _load().values():
        out.append({
            "id": a["id"], "title": a["title"], "short": a["short"],
            "year": a["year"], "status": a["status"],
            "source_verified": a["source_verified"],
            "section_count": len(a["sections"]),
        })
    # in-force first, then by title
    out.sort(key=lambda x: (x["status"] != "in_force", x["title"]))
    return out


def get_act(act_id: str) -> dict | None:
    a = _load().get(act_id)
    if not a:
        return None
    return {
        "id": a["id"], "title": a["title"], "short": a["short"], "year": a["year"],
        "status": a["status"], "source_verified": a["source_verified"],
        "source_url": a["source_url"],
        "sections": [{"num": s["num"], "title": s["title"]} for s in a["sections"]],
    }


def get_section(act_id: str, num: str) -> dict | None:
    a = _load().get(act_id)
    if not a:
        return None
    for s in a["sections"]:
        if str(s["num"]) == str(num):
            return {
                "act_id": a["id"], "act_title": a["title"], "year": a["year"],
                "status": a["status"], "source_verified": a["source_verified"],
                "source_url": a["source_url"],
                "num": s["num"], "title": s["title"], "text": s["text"],
            }
    return None


# Practitioner shorthand that appears NOWHERE in the statutory text. An advocate searches
# "anticipatory bail"; the Code says "Direction for grant of bail to person apprehending
# arrest" and never once uses the colloquial term.
#
# Found 2026-07-30 in an unusually pointed way: test_search_finds_sections had been passing
# only because "anticipatory bail" happened to occur inside CrPC s.38's CONTAMINATED text —
# an amendment clause quoting s.438 that had overwritten the real provision. Repairing the
# corpus removed the phrase and exposed a gap that had always been there. The test was green
# because the corpus was wrong.
#
# Each alias maps to wording that genuinely exists, so it resolves in BOTH the old Code and
# its 2023 successor (CrPC s.438 / BNSS s.482, CrPC s.154 / BNSS s.173).
_COLLOQUIAL_TERMS: dict[str, tuple[str, ...]] = {
    "anticipatory bail":         ("bail to person apprehending arrest",),
    "first information report":  ("information in cognizable cases",),
    "fir":                       ("information in cognizable cases",),
}


def search(query: str, limit: int = 30) -> list[dict]:
    """Case-insensitive match over section number/title/text across all acts.

    Colloquial legal shorthand is expanded to the statutory wording it refers to; see
    ``_COLLOQUIAL_TERMS``. Expansion is exact-match on the whole query, never substring, so
    a search for "fir" cannot be triggered by "firm", "confirm" or "first".
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    # Expanded wording FIRST, then the literal query. Order matters twice over: a short
    # alias like "fir" substring-matches "first", "firm" and "confirm" across the whole
    # corpus, so searching it literally would bury CrPC s.154 under noise and could exhaust
    # `limit` before ever reaching it. Putting the statutory phrasing first also ranks the
    # provision the user meant above incidental mentions.
    terms = (*_COLLOQUIAL_TERMS.get(q, ()), q)
    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for term in terms:
        for a in _load().values():
            for s in a["sections"]:
                key = (a["id"], s["num"])
                if key in seen:
                    continue
                hay = f"{s['num']} {s['title']} {s['text']}".lower()
                if term in hay:
                    seen.add(key)
                    hits.append({
                        "act_id": a["id"], "act_title": a["title"],
                        "num": s["num"], "title": s["title"],
                        "source_verified": a["source_verified"],
                    })
                    if len(hits) >= limit:
                        return hits
    return hits
