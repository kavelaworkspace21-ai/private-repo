"""
Case-law retrieval — Indian Kanoon API connector.

NO-HALLUCINATION GUARANTEE:
  This module returns case-law context ONLY from the live Indian Kanoon API. When the
  integration is disabled it returns empty so the agent abstains from citing any
  judgment — it NEVER invents case names, citations, or holdings.

ENABLEMENT (both required, opt-in):
  KANOON_ENABLED=true  AND  INDIAN_KANOON_API_KEY=<key>
  This API is billed per call, so a key alone is deliberately NOT enough to spend money.
  Get a key at https://api.indiankanoon.org/

API docs: https://api.indiankanoon.org/  (POST, header: "Authorization: Token <key>")
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

KANOON_API_KEY = os.getenv("INDIAN_KANOON_API_KEY", "")
KANOON_SEARCH_URL = "https://api.indiankanoon.org/search/"
TOP_N = 5

# Indian Kanoon is the ONE genuinely billed dependency (per-call). Presence of a key is
# NOT consent to spend: a key sitting in .env for a one-off test used to be enough to bill
# every dashboard load. Enablement is therefore an EXPLICIT opt-in, defaulting to OFF, and
# BOTH the flag and a key are required. Set KANOON_ENABLED=true only where the spend is
# intended.
_TRUTHY = {"1", "true", "yes", "on"}
KANOON_ENABLED = os.getenv("KANOON_ENABLED", "").strip().lower() in _TRUTHY

# "Is it still good law?" — we cannot verify treatment (overruled/reversed/distinguished)
# from the basic API, so we NEVER assert a judgment is good law. We attach this honest
# caveat to every result and bar the agent from claiming treatment either way.
GOOD_LAW_CAVEAT = (
    "Good-law status NOT verified: this judgment may since have been overruled, reversed, "
    "or distinguished. Check its subsequent history / a citator before relying on it."
)

# ── In-memory TTL cache (Indian Kanoon bills per call) ──────────────────────────
import time as _time
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 60 * 60 * 24          # 24h — statutes/judgments don't change intraday
_CACHE_MAX = 500


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if hit and (_time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    if hit:
        _CACHE.pop(key, None)
    return None


def _cache_put(key: str, value):
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)), None)   # drop oldest
    _CACHE[key] = (_time.time(), value)


def is_enabled() -> bool:
    """Live case law is available only with an explicit opt-in AND a key.

    Read through the module attributes (not the captured locals) so tests and runtime
    toggles both take effect.
    """
    return bool(KANOON_ENABLED) and bool(KANOON_API_KEY)


def retrieve_cases(query: str) -> str:
    """
    Return a formatted block of real judgments for the query, or "" if unavailable.
    Only genuine API results are returned — no fabrication, ever.
    """
    if not is_enabled():
        logger.info("Live case law disabled (needs KANOON_ENABLED=true + a key) — abstaining.")
        return ""

    cards = search_cases(query, limit=TOP_N)   # cached, no fabrication
    if not cards:
        return ""

    lines = []
    for c in cards:
        meta = " · ".join(p for p in [c["court"], c["date"], c["citation"]] if p)
        extra = f" · cited by {c['cited_by']}" if c["cited_by"].isdigit() else ""
        block = f"• {c['title']}\n  {meta}{extra}"
        if c["snippet"]:
            block += f"\n  Excerpt: “{c['snippet']}”"
        block += f"\n  [source: {c['url']}]"
        lines.append(block)

    return (
        "VERIFIED CASE LAW (live from Indian Kanoon — cite ONLY these judgments, always "
        "with the link. The 'Excerpt' is a verbatim snippet from the judgment; you may "
        "summarise ONLY what the title/excerpt actually shows and must NOT state any "
        "holding, ratio, or outcome you cannot see in it. GOOD-LAW STATUS IS UNVERIFIED — "
        "never state or imply a judgment is still good law / has been overruled; tell the "
        "advocate to check its subsequent history. Tell them to open the link to read the "
        "full judgment before relying on it):\n" + "\n".join(lines)
        + "\n\n⚠ " + GOOD_LAW_CAVEAT
    )


KANOON_DOC_URL = "https://api.indiankanoon.org/doc/{tid}/"


def fetch_document(tid: str) -> dict | None:
    """Fetch a full judgment by its Indian Kanoon id. Returns metadata + plain text."""
    if not is_enabled() or not tid:
        return None
    ckey = f"doc::{tid}"
    cached = _cache_get(ckey)
    if cached is not None:
        return cached
    try:
        import httpx, re
        headers = {"Authorization": f"Token {KANOON_API_KEY}"}
        with httpx.Client(timeout=30) as client:
            resp = client.post(KANOON_DOC_URL.format(tid=tid), headers=headers)
        if resp.status_code != 200:
            return None
        d = resp.json()
        html = d.get("doc", "") or ""
        text = re.sub(r"<[^>]+>", " ", html)          # strip tags
        text = re.sub(r"\s+", " ", text).strip()
        result = {
            "tid": tid,
            "title": _s(d.get("title")),
            "court": _s(d.get("docsource")),
            "date": _s(d.get("publishdate")),
            "cited_by": _s(d.get("numcitedby")),
            "text": text,
            "url": f"https://indiankanoon.org/doc/{tid}/",
        }
        _cache_put(ckey, result)
        return result
    except Exception as e:
        logger.warning(f"Indian Kanoon doc fetch failed: {e}")
        return None


def summarize_case(tid: str) -> dict | None:
    """
    Brief, source-grounded summary of a judgment for at-a-glance review.
    The summary is derived ONLY from the fetched judgment text (no outside knowledge),
    so it does not introduce hallucinated facts. Always returns the verifiable link.
    Falls back to an extractive excerpt if no OpenAI key is configured.
    """
    doc = fetch_document(tid)
    if not doc:
        return None

    body = doc["text"][:12000]   # cap tokens; summary is grounded in this slice
    summary = ""
    from app.ai.llm_config import ai_config
    cfg = ai_config()
    if cfg["api_key"] and body:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
            resp = client.chat.completions.create(
                model=cfg["model"],
                temperature=0.1,
                max_tokens=400,
                messages=[
                    {"role": "system", "content":
                        "You summarise Indian court judgments for an advocate. Use ONLY the "
                        "text provided — do not add any fact, section, or holding not present "
                        "in it. 4-6 sentence neutral summary: parties, core issue, what the "
                        "court held. No outcome guarantees. If the text is insufficient, say so."},
                    {"role": "user", "content":
                        f"Title: {doc['title']}\nCourt: {doc['court']} ({doc['date']})\n\n"
                        f"Judgment text:\n{body}"},
                ],
            )
            summary = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"Case summary generation failed: {e}")

    if not summary:
        # Extractive fallback: verbatim opening of the judgment (no model, no risk)
        summary = body[:900].strip() + ("…" if len(body) > 900 else "")

    return {
        "title": doc["title"], "court": doc["court"], "date": doc["date"],
        "cited_by": doc["cited_by"], "summary": summary, "url": doc["url"],
        "good_law": "unverified",
        "disclaimer": "AI summary grounded in the linked judgment. " + GOOD_LAW_CAVEAT,
    }


def _s(v) -> str:
    """Coerce any API field (str | int | None) to a clean string."""
    return "" if v is None else str(v).strip()


def _clean_snippet(html) -> str:
    """Strip the API's <b> highlight tags and collapse whitespace."""
    import re
    text = re.sub(r"</?b>", "", _s(html))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def search_cases(query: str, limit: int = TOP_N) -> list[dict]:
    """
    Structured case results for UI/API use (at-a-glance cards + verifiable link).
    Cached for 24h to limit billed API calls. Returns [] if no key/results. No fabrication.
    """
    if not is_enabled():
        return []
    ckey = f"search::{limit}::{query.strip().lower()}"
    cached = _cache_get(ckey)
    if cached is not None:
        return cached
    try:
        import httpx
        headers = {"Authorization": f"Token {KANOON_API_KEY}"}
        with httpx.Client(timeout=20) as client:
            resp = client.post(KANOON_SEARCH_URL,
                               params={"formInput": query, "pagenum": 0},
                               headers=headers)
        if resp.status_code != 200:
            return []
        docs = (resp.json().get("docs") or [])[:limit]
    except Exception as e:
        logger.warning(f"Indian Kanoon search failed: {e}")
        return []

    out = [_card_from_doc(d) for d in docs]
    _cache_put(ckey, out)
    return out


LATEST_QUERY = "supreme court sortby:mostrecent"


def _plausible_year(date_str: str) -> bool:
    """Drop entries whose parsed year is implausible (Kanoon occasionally returns junk dates)."""
    import re
    m = re.search(r"(\d{4})", date_str or "")
    if not m:
        return True
    return 1900 <= int(m.group(1)) <= 2027


def latest_judgments(limit: int = 6) -> list[dict]:
    """
    Recent judgments for the dashboard 'Latest from the courts' feed. Source-grounded (real Indian
    Kanoon results with verifiable links), cached 24h to limit billed calls, [] if no key. Never
    fabricates. Good-law status remains UNVERIFIED (caveat carried on every card).
    """
    if not is_enabled():
        return []
    ckey = f"latest::{limit}"
    cached = _cache_get(ckey)
    if cached is not None:
        return cached
    cards = [c for c in search_cases(LATEST_QUERY, limit=limit * 2) if _plausible_year(c.get("date", ""))]
    out = cards[:limit]
    _cache_put(ckey, out)
    return out


def _card_from_doc(d: dict) -> dict:
    """Map one Indian Kanoon search doc to a UI card (pure; carries good-law caveat)."""
    tid = _s(d.get("tid"))
    return {
        "title": _s(d.get("title")),
        "court": _s(d.get("docsource")),
        "date": _s(d.get("publishdate")),
        "citation": _s(d.get("citation")),
        "cited_by": _s(d.get("numcitedby")),
        "snippet": _clean_snippet(d.get("headline") or d.get("fragment")),
        "url": f"https://indiankanoon.org/doc/{tid}/" if tid else "",
        "good_law": "unverified",
        "good_law_caveat": GOOD_LAW_CAVEAT,
    }
