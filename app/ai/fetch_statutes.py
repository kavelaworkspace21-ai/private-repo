"""
Official-PDF downloader for the statute registry (companion to ingest_statutes.py).

Downloads each Act's OFFICIAL PDF from India Code into data/source_pdfs/<act_id>.pdf, validating
that the bytes are a real PDF (rejects anti-bot HTML interstitials). For acts whose registry URL is a
DSpace `handle` page, it fetches that page and resolves the real English bitstream `.pdf` link
(English = the `/1/` bitstream whose filename does not start with 'h'/'H' — Hindi is the `/2/` 'hh' file).

NO AI in the loop — pure HTTP + regex. Authenticity is then enforced by ingest_statutes.py (SHA-256 +
deterministic pdfplumber extraction). Legal basis + sources: docs/legal/CORPUS_SOURCES_AND_LEGALITY.md.

USAGE:
    python -m app.ai.fetch_statutes all          # download every registry act's PDF
    python -m app.ai.fetch_statutes bns_2023      # one act
"""
import re
import sys
import logging
from pathlib import Path

import requests

from app.ai.ingest_statutes import STATUTE_REGISTRY, PDF_DIR

logger = logging.getLogger(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_BITSTREAM_RE = re.compile(r'href="([^"]*bitstream[^"]*\.pdf[^"]*)"', re.IGNORECASE)


def _is_pdf(content: bytes) -> bool:
    return content[:5] == b"%PDF-"


def _english_first(links: list[str]) -> list[str]:
    """Order candidate bitstream links: English (filename not starting h/H, '/1/') before Hindi."""
    def score(u: str) -> tuple:
        fname = u.rstrip("/").split("/")[-1]
        is_hindi = fname[:1] in ("h", "H") or "hindi" in u.lower()
        return (1 if is_hindi else 0, 0 if "/1/" in u else 1)
    return sorted(dict.fromkeys(links), key=score)


def _resolve_links(landing: str) -> list[str]:
    r = requests.get(landing, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    out = []
    for m in _BITSTREAM_RE.finditer(r.text):
        u = m.group(1).replace("&amp;", "&")
        if not u.startswith("http"):
            u = "https://www.indiacode.nic.in" + u
        out.append(u)
    return _english_first(out)


def fetch(act_id: str) -> dict:
    meta = STATUTE_REGISTRY[act_id]
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    dest = PDF_DIR / f"{act_id}.pdf"
    if dest.exists() and _is_pdf(dest.read_bytes()):
        return {"act_id": act_id, "status": "already_present", "bytes": dest.stat().st_size}

    candidates: list[str] = []
    if meta["source_url"].lower().endswith(".pdf"):
        candidates.append(meta["source_url"])
    try:
        candidates += _resolve_links(meta["landing"])
    except Exception as e:
        logger.warning(f"{act_id}: could not resolve landing page: {e}")

    for url in candidates:
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
            if r.ok and _is_pdf(r.content):
                dest.write_bytes(r.content)
                return {"act_id": act_id, "status": "downloaded", "bytes": len(r.content), "url": url}
        except Exception as e:
            logger.warning(f"{act_id}: {url} failed: {e}")
    return {"act_id": act_id, "status": "FAILED", "tried": len(candidates)}


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    targets = list(STATUTE_REGISTRY) if (not argv or argv[0] == "all") else argv
    for aid in targets:
        r = fetch(aid)
        print(f"{r['status']:16} {aid}" + (f"  ({r.get('bytes',0)//1024} KB)" if r.get("bytes") else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
