"""
Corpus versioning + upstream-change detection (Roadmap P3 — continuous update pipeline).

The corpus is only trustworthy while it matches the official source. This module makes
staleness VISIBLE and auditable:

  * corpus_manifest()  — per-act provenance snapshot (sha256, fetched_on, status, counts)
    read from the source-verified fulltext files. No network.
  * corpus_version()   — a single fingerprint over every act's sha256: changes iff any
    act's verified text changes. Stamped into status payloads and logs.
  * check_upstream()   — re-downloads each act's OFFICIAL bitstream PDF and compares its
    sha256 with the one we ingested. Reports which acts changed upstream (amended /
    re-consolidated by India Code). IT NEVER RE-INGESTS: per doctrine, re-ingestion goes
    through the human-supervised slice discipline (landmark-content verification before
    any reseed). The weekly scheduler job + admin endpoint only surface the drift.

The Income-tax 1961 repeal (found 2026-07-16, three months after it happened) is exactly
the failure mode this exists to catch early.
"""
import json
import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

FULLTEXT_DIR = Path(__file__).parent.parent / "legal_corpus" / "fulltext"
CHECK_RESULT_PATH = Path(__file__).parent.parent / "legal_corpus" / "upstream_check.json"
MANUAL_VERIF_PATH = Path(__file__).parent.parent / "legal_corpus" / "manual_verifications.json"


def corpus_manifest() -> dict:
    """Per-act provenance from the verified fulltext files (offline, fast)."""
    acts = []
    for f in sorted(FULLTEXT_DIR.glob("*.fulltext.json")):
        try:
            act = json.load(open(f, encoding="utf-8"))["acts"][0]
        except Exception as e:
            logger.warning(f"corpus_manifest: unreadable {f.name}: {e}")
            continue
        src = act.get("source", {})
        # Hash the PARSED text too: the source sha256 alone misses parser-level changes to
        # the same official PDF (2026-07-20: Limitation 137→169 / IPC stub recovery would
        # have left the fingerprint unmoved — breaking "changes iff verified text changes").
        content = hashlib.sha256()
        for s in act.get("sections", []):
            content.update(f"{s.get('num','')}\x1f{s.get('title','')}\x1f{s.get('text','')}\x1e"
                           .encode("utf-8", "replace"))
        acts.append({
            "id": act["id"],
            "title": act.get("title", ""),
            "status": act.get("status", "in_force"),
            "repealed_by": act.get("repealed_by", ""),
            "sections": len(act.get("sections", [])),
            "sha256": src.get("sha256", ""),
            "content_sha": content.hexdigest()[:12],
            "fetched_on": src.get("fetched_on", ""),
            "source_url": src.get("url", ""),
        })
    return {
        "acts": acts,
        "act_count": len(acts),
        "section_count": sum(a["sections"] for a in acts),
        "corpus_version": corpus_version(acts),
        "anomalies": corpus_anomalies(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def corpus_anomalies() -> list[dict]:
    """Structural anomalies in the source-verified corpus that need LEGAL REVIEW — recorded
    so they are never invisible.

    Currently detects **duplicate section numbers** within an act. The vector seed keeps the
    FIRST occurrence and does not embed the rest (deterministic, so a stray fragment can't wipe
    the corpus — see vector_store._seed_collection). That de-dup is a mechanical safety choice,
    NOT a legal adjudication of which provision is canonical. The classic case is IPC ``354E``,
    where the official source carries two DIFFERENT provisions under the same number
    ("Sextortion" and "Liability of a person present who fails to prevent an offence under
    s.354/354A-D"): only the first is retrievable, and a human must decide the correct treatment.
    Both texts remain in the fulltext (source evidence preserved); this report surfaces the drop.
    """
    from collections import defaultdict
    anomalies: list[dict] = []
    for f in sorted(FULLTEXT_DIR.glob("*.fulltext.json")):
        try:
            act = json.load(open(f, encoding="utf-8"))["acts"][0]
        except Exception:
            continue
        by_num: dict[str, list] = defaultdict(list)
        for s in act.get("sections", []):
            by_num[str(s.get("num", ""))].append(s)
        for num, group in by_num.items():
            if len(group) > 1:
                anomalies.append({
                    "act_id": act["id"],
                    "act_title": act.get("title", ""),
                    "type": "duplicate_section_number",
                    "section": num,
                    "count": len(group),
                    "kept_in_index": {"title": group[0].get("title", ""),
                                      "page": group[0].get("page", "")},
                    "dropped_from_index": [
                        {"title": g.get("title", ""), "page": g.get("page", "")}
                        for g in group[1:]
                    ],
                    "treatment": "vector index keeps the FIRST occurrence (deterministic); later "
                                 "duplicates stay in fulltext but are not embedded",
                    "review_state": "PENDING_LEGAL_REVIEW",
                })
    return anomalies


def corpus_version(acts: list[dict] | None = None) -> str:
    """12-hex fingerprint over every act's source sha256 AND parsed-content sha — changes
    iff the verified text changes (source republished OR the parse of it changed)."""
    if acts is None:
        acts = corpus_manifest()["acts"]
    basis = "|".join(f"{a['id']}:{a['sha256']}:{a.get('content_sha', '')}"
                     for a in sorted(acts, key=lambda x: x["id"]))
    return hashlib.sha256(basis.encode()).hexdigest()[:12]


def _fetch_sha256(url: str, timeout: float = 45.0) -> str:
    """sha256 of the OFFICIAL bitstream at `url` (streamed; raises on HTTP error)."""
    import httpx
    h = hashlib.sha256()
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as r:
        r.raise_for_status()
        for chunk in r.iter_bytes():
            h.update(chunk)
    return h.hexdigest()


def load_manual_verifications() -> dict:
    """Human currency sign-offs for sources the automated drift check can't fetch (WAF-protected
    PDFs, landing-page URLs). Keys are act_ids; keys starting with '_' are docs, not records."""
    try:
        return json.loads(MANUAL_VERIF_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _manual_stale(rec: dict, today: datetime | None = None) -> bool:
    """A manual verification is stale if it has no date, or its next_review has passed."""
    if not rec or not rec.get("last_verified_at"):
        return True
    nxt = rec.get("next_review")
    if not nxt:
        return False
    try:
        due = date.fromisoformat(nxt)   # tz-less calendar date; DTZ-clean, no %z needed
    except ValueError:
        return True
    now = (today or datetime.now(timezone.utc)).date()
    return now > due


def record_manual_verification(act_id: str, reviewer: str, source_sha256: str = "",
                               next_review_days: int = 90, note: str = "") -> dict:
    """Record a HUMAN's confirmation that an un-fetchable source is still current. Invoked by
    the owner/reviewer AFTER they check the official source — never automatically (the agent
    cannot verify a WAF-protected page, and must never fabricate currency)."""
    from app.util.time import utcnow
    store = load_manual_verifications()
    now = utcnow()
    store[act_id] = {
        "last_verified_at": now.strftime("%Y-%m-%d"),
        "reviewer": reviewer,
        "source_sha256": source_sha256,
        "next_review": (now + timedelta(days=next_review_days)).strftime("%Y-%m-%d"),
        "note": note,
    }
    MANUAL_VERIF_PATH.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
    return store[act_id]


def _currency(act_id: str, status: str, manual: dict, today: datetime | None = None) -> dict:
    """Honest currency for a drift result. An errored/skipped check is NEVER 'current' — it
    falls back to a valid manual verification, or is reported UNVERIFIED."""
    if status == "unchanged":
        return {"state": "verified_current_automated"}
    if status == "UPDATED_UPSTREAM":
        return {"state": "drift_detected"}
    # error / skipped_no_pdf → the automated check proved nothing about currency
    rec = manual.get(act_id)
    if rec and not _manual_stale(rec, today):
        return {"state": "manually_verified", "last_verified_at": rec.get("last_verified_at"),
                "reviewer": rec.get("reviewer"), "next_review": rec.get("next_review")}
    return {"state": "UNVERIFIED",
            "detail": "automated check could not fetch the source and no current manual "
                      "verification exists — currency is unknown, do NOT treat as current"}


def check_upstream(act_ids: list[str] | None = None, fetcher=None) -> dict:
    """Compare each act's stored sha256 with the live official bitstream.

    Returns {checked_on, corpus_version, results: {act_id: {status, detail}}} where status is
      unchanged        — upstream byte-identical to what we ingested
      UPDATED_UPSTREAM — India Code republished the file (amendment/reconsolidation):
                         schedule a re-ingest SLICE with landmark verification
      skipped_no_pdf   — the stored source URL is a handle page, not a direct PDF
      error            — network/HTTP failure (detail carries the reason)

    Never mutates the corpus. Result also persisted to upstream_check.json for the
    status endpoint. `fetcher` is injectable for tests (url -> sha256 hex).
    """
    fetch = fetcher or _fetch_sha256
    manifest = corpus_manifest()
    results: dict[str, dict] = {}
    for a in manifest["acts"]:
        if act_ids and a["id"] not in act_ids:
            continue
        url, stored = a["source_url"], a["sha256"]
        if not url or ".pdf" not in url.lower():
            results[a["id"]] = {"status": "skipped_no_pdf",
                                "detail": "source URL is a handle page, not a direct PDF"}
            continue
        try:
            live = fetch(url)
        except Exception as e:
            results[a["id"]] = {"status": "error", "detail": str(e)[:200]}
            continue
        if live == stored:
            results[a["id"]] = {"status": "unchanged", "detail": ""}
        else:
            results[a["id"]] = {
                "status": "UPDATED_UPSTREAM",
                "detail": f"stored {stored[:12]}… vs live {live[:12]}… — official file "
                          f"republished; re-ingest via the slice discipline (landmark "
                          f"verification before reseed).",
            }
            logger.warning(f"Corpus drift: {a['id']} changed upstream ({url})")

    # Attach honest currency to every result: an errored/skipped source is never labelled
    # current — it resolves to a valid manual verification, or is reported UNVERIFIED.
    manual = load_manual_verifications()
    for act_id, r in results.items():
        r["currency"] = _currency(act_id, r["status"], manual)
    unverified = sum(1 for r in results.values() if r["currency"]["state"] == "UNVERIFIED")
    for act_id, r in results.items():
        if r["currency"]["state"] == "UNVERIFIED":
            logger.warning(f"Corpus currency UNVERIFIED for {act_id} — automated check "
                           f"{r['status']}, no current manual verification.")

    out = {
        "checked_on": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus_version": manifest["corpus_version"],
        "results": results,
        "summary": {
            "checked": len(results),
            "updated_upstream": sum(1 for r in results.values() if r["status"] == "UPDATED_UPSTREAM"),
            "errors": sum(1 for r in results.values() if r["status"] == "error"),
            "skipped": sum(1 for r in results.values() if r["status"] == "skipped_no_pdf"),
            "unverified_currency": unverified,
        },
    }
    try:
        CHECK_RESULT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not persist upstream check: {e}")
    return out


_version_cache: dict = {"value": None, "expires": 0.0}


def cached_corpus_version(ttl_seconds: float = 600.0) -> str:
    """corpus_version() with a 10-minute cache — cheap enough for every chat answer's
    Sources footer (reads ~43 JSON files on a cold call, nothing after)."""
    import time
    now = time.monotonic()
    if _version_cache["value"] and now < _version_cache["expires"]:
        return _version_cache["value"]
    v = corpus_version()
    _version_cache.update({"value": v, "expires": now + ttl_seconds})
    return v


def last_upstream_check() -> dict | None:
    """The persisted result of the most recent check_upstream run, if any."""
    try:
        return json.loads(CHECK_RESULT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


if __name__ == "__main__":
    # CLI (S0 / Appendix B #1): reproducible corpus fingerprint for CI + release checks.
    #   python -m app.ai.corpus_updates                 -> prints the 12-hex fingerprint
    #   python -m app.ai.corpus_updates --fingerprint   -> same (explicit)
    #   python -m app.ai.corpus_updates --manifest       -> full per-act manifest as JSON
    import argparse

    ap = argparse.ArgumentParser(description="Juriscite corpus fingerprint / manifest.")
    ap.add_argument("--fingerprint", action="store_true",
                    help="print the 12-hex corpus fingerprint (default action)")
    ap.add_argument("--manifest", action="store_true",
                    help="print the full corpus manifest as JSON")
    args = ap.parse_args()
    if args.manifest:
        print(json.dumps(corpus_manifest(), indent=2))
    else:
        print(corpus_version())
