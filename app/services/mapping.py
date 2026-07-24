"""
Old↔new criminal-law section mapping (IPC↔BNS, CrPC↔BNSS, IEA↔BSA).

Data lives in legal_corpus/statute_mapping.json and is AI-compiled, NOT yet advocate-
verified (Gate G8). Every result carries that caveat so it's never presented as final.
"""
import re
import json
import functools
from pathlib import Path

_PATH = Path(__file__).parent.parent / "legal_corpus" / "statute_mapping.json"

# Normalise the many ways advocates name the codes.
_OLD_ALIASES = {
    "ipc": "IPC", "indian penal code": "IPC", "penal code": "IPC",
    "crpc": "CrPC", "cr.p.c": "CrPC", "code of criminal procedure": "CrPC",
    "iea": "IEA", "indian evidence act": "IEA", "evidence act": "IEA", "evidence": "IEA",
}
_NEW_ALIASES = {
    "bns": "BNS", "bharatiya nyaya sanhita": "BNS",
    "bnss": "BNSS", "bharatiya nagarik suraksha sanhita": "BNSS",
    "bsa": "BSA", "bharatiya sakshya adhiniyam": "BSA",
}


@functools.lru_cache(maxsize=1)
def _data() -> dict:
    try:
        return json.load(open(_PATH, encoding="utf-8"))
    except Exception:
        return {"mappings": [], "advocate_approved": False, "verification_status": "missing"}


def _caveat() -> dict:
    d = _data()
    return {
        "advocate_approved": d.get("advocate_approved", False),
        "verification_status": d.get("verification_status", "ai_compiled_unverified"),
        "disclaimer": "AI-compiled mapping, pending senior-advocate verification. "
                      "Confirm the exact new-section text at indiacode.nic.in before relying on it.",
    }


def _norm_act(name: str) -> str | None:
    key = (name or "").strip().lower().rstrip(".")
    if key.upper() in ("IPC", "CRPC", "IEA", "BNS", "BNSS", "BSA"):
        return {"crpc": "CrPC"}.get(key, key.upper())
    return _OLD_ALIASES.get(key) or _NEW_ALIASES.get(key)


def _norm_sec(section: str) -> str:
    return re.sub(r"(?i)^(section|sec\.?|s\.|§|article|art\.)\s*", "", (section or "").strip()).strip()


def lookup_old(act: str, section: str) -> dict | None:
    """Old (IPC/CrPC/IEA) section → new equivalent."""
    a, s = _norm_act(act), _norm_sec(section)
    if not a:
        return None
    base = re.match(r"\d+[A-Z]*", s)
    base = base.group(0) if base else s
    for m in _data().get("mappings", []):
        if m["old"] == a and (m["old_section"] == s or m["old_section"] == base):
            return {**m, **_caveat()}
    return None


def lookup_new(act: str, section: str) -> dict | None:
    """New (BNS/BNSS/BSA) section → old equivalent."""
    a, s = _norm_act(act), _norm_sec(section)
    if not a:
        return None
    base = re.match(r"\d+[A-Z]*", s)
    base = base.group(0) if base else s
    for m in _data().get("mappings", []):
        if m["new"] == a and (m["new_section"] == s or m["new_section"].startswith(base)):
            return {**m, **_caveat()}
    return None


# Detect "IPC 420", "Section 420 IPC", "420 of CrPC", "s.65B IEA" in free text.
_PATTERNS = [
    re.compile(r"\b(IPC|CrPC|Cr\.?P\.?C|IEA)\b[^\d]{0,12}(\d{1,4}[A-Z]{0,2})", re.IGNORECASE),
    re.compile(r"\b(?:section|sec\.?|s\.|§)\s*(\d{1,4}[A-Z]{0,2})\s+(?:of\s+)?(IPC|CrPC|Cr\.?P\.?C|IEA|Indian Penal Code|Code of Criminal Procedure|Indian Evidence Act)", re.IGNORECASE),
]


def detect_old_refs(text: str) -> list[dict]:
    """Find old-code section references in text and return their new-code mappings."""
    if not text:
        return []
    found, seen = [], set()
    for rx in _PATTERNS:
        for m in rx.finditer(text):
            groups = m.groups()
            # group order differs per pattern; figure out which is act vs section
            act = next((g for g in groups if g and re.search(r"[A-Za-z]", g)), None)
            sec = next((g for g in groups if g and re.fullmatch(r"\d{1,4}[A-Z]{0,2}", g)), None)
            if not act or not sec:
                continue
            hit = lookup_old(act, sec)
            if hit:
                k = (hit["old"], hit["old_section"])
                if k not in seen:
                    seen.add(k)
                    found.append(hit)
    return found


def all_mappings() -> list[dict]:
    return _data().get("mappings", [])
