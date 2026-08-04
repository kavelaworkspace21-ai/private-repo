"""
Reference format skeletons for the AI Drafting Engine (templates/drafts/).

The engine injects the matching skeleton into the generation prompt as a FORMAT
REFERENCE, so drafts follow authentic Indian drafting structure (cause title,
numbered paragraphs, prayer, verification) instead of the model improvising one.
Skeletons carry [●] placeholders; the model fills them from the advocate's facts
and MUST keep [●] wherever a fact was not supplied (never invent).

Structures follow common professional convention. advocate_approved=false until
G8 (senior-advocate sign-off) — tracked in manifest.json.
"""
import functools
import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "drafts"


@functools.lru_cache(maxsize=1)
def _manifest() -> dict:
    try:
        data = json.loads((TEMPLATES_DIR / "manifest.json").read_text(encoding="utf-8"))
        return data.get("templates", {})
    except Exception:
        return {}


@functools.lru_cache(maxsize=32)
def get_skeleton(doc_type: str) -> str | None:
    """Verbatim skeleton text for a registered document type, or None."""
    meta = _manifest().get(doc_type)
    if not meta:
        return None
    try:
        return (TEMPLATES_DIR / meta["file"]).read_text(encoding="utf-8")
    except Exception:
        return None


def match_skeleton(free_text: str) -> tuple[str, str] | None:
    """For custom documents: pick the closest skeleton by keyword score.
    Returns (template_id, skeleton_text) or None if nothing plausibly matches."""
    text = (free_text or "").lower()
    if not text:
        return None
    best_id, best_score = None, 0
    for tid, meta in _manifest().items():
        score = 0
        for kw in meta.get("keywords", []):
            if kw in text:
                # longer keyword = more specific = stronger signal
                score += 1 + len(kw.split())
        if score > best_score:
            best_id, best_score = tid, score
    if best_id and best_score >= 2:          # require a reasonably specific match
        skel = get_skeleton(best_id)
        if skel:
            return best_id, skel
    return None


def list_templates() -> list[dict]:
    return [{"id": tid, "label": m.get("label", tid)} for tid, m in _manifest().items()]


def get_label(template_id: str) -> str | None:
    m = _manifest().get(template_id)
    return m.get("label", template_id) if m else None


def resolve_format(doc_type: str, fields: dict) -> tuple[str | None, str | None]:
    """(format_label, skeleton_text) the engine will use for this request.
    Registered types use their own skeleton; custom documents are keyword-matched.
    (None, None) when nothing applies — generation proceeds unguided but safe."""
    skeleton = get_skeleton(doc_type)
    if skeleton is not None:
        return get_label(doc_type), skeleton
    if doc_type == "custom_document":
        hit = match_skeleton(f"{fields.get('document_title', '')} {fields.get('instructions', '')}")
        if hit:
            return get_label(hit[0]), hit[1]
    return None, None
