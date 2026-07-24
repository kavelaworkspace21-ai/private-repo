"""
eCourts connector — READ-ONLY, official/authorized API only (CLAUDE.md, authorized 2026-06-19).

Pulls a matter's hearing history / next date by CNR (Case Number Record) so it can be
mirrored into the user's Court Diary. NEVER scrapes and never bypasses CAPTCHAs.

Configuration (.env):
  ECOURTS_API_KEY   — your authorized key
  ECOURTS_API_BASE  — your provider's base URL (REQUIRED to enable; left blank = disabled)

The exact request/response shape varies by provider, so this module is defensive:
it tries common patterns and normalises common field names. Confirm the provider's docs
and adjust `_request` / `normalise_hearings` if your provider differs.
"""
import os
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

API_KEY = os.getenv("ECOURTS_API_KEY", "")
API_BASE = os.getenv("ECOURTS_API_BASE", "").rstrip("/")


def is_enabled() -> bool:
    """Enabled only when both a key AND a base URL are configured."""
    return bool(API_KEY and API_BASE)


def status() -> dict:
    return {
        "enabled": is_enabled(),
        "has_key": bool(API_KEY),
        "has_base_url": bool(API_BASE),
    }


def _request(cnr: str) -> dict | None:
    """
    Fetch raw case data for a CNR. Tries a POST {base} with json {cnr} and bearer auth,
    which is the common shape for eCourts API vendors. Returns parsed JSON or None.
    """
    if not is_enabled():
        return None
    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "x-api-key": API_KEY,           # some vendors use this header instead
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(API_BASE, headers=headers, json={"cnr": cnr})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"eCourts request failed for CNR {cnr}: {e}")
        return None


def _parse_date(value) -> date | None:
    """Accept the many date formats eCourts feeds use."""
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()  # noqa: DTZ007 — eCourts cause-list dates are tz-less; parsed to date only
        except ValueError:
            continue
    return None


def normalise_hearings(raw: dict) -> list[dict]:
    """
    Map a provider's case payload to a list of {date, purpose, court, judge} hearings.
    Looks for common keys; returns [] if none found (so callers degrade gracefully).
    """
    if not isinstance(raw, dict):
        return []
    data = raw.get("data") or raw.get("result") or raw

    # Hearing history can live under several keys depending on the vendor.
    history = (
        data.get("case_history") or data.get("history") or
        data.get("hearing_history") or data.get("hearings") or []
    )
    court = (data.get("court_name") or data.get("court") or
             data.get("establishment_name") or "")
    out = []
    for h in history if isinstance(history, list) else []:
        if not isinstance(h, dict):
            continue
        d = _parse_date(h.get("business_date") or h.get("date") or
                        h.get("next_date") or h.get("hearing_date"))
        if not d:
            continue
        out.append({
            "date": d,
            "purpose": (h.get("purpose") or h.get("business") or
                        h.get("stage") or "Hearing"),
            "court": court,
            "judge": h.get("judge") or h.get("coram") or "",
        })

    # Also surface the upcoming "next hearing date" if provided separately.
    nxt = _parse_date(data.get("next_hearing_date") or data.get("next_date"))
    if nxt and not any(o["date"] == nxt for o in out):
        out.append({"date": nxt,
                    "purpose": data.get("purpose_of_next_hearing") or "Next hearing",
                    "court": court, "judge": ""})
    return out


def fetch_hearings(cnr: str) -> list[dict]:
    """Public: return normalised hearings for a CNR (empty if disabled/not found)."""
    raw = _request(cnr)
    if not raw:
        return []
    return normalise_hearings(raw)
