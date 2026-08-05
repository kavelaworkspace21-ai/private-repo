"""Diff the corpus against a saved snapshot — what actually changed between two fingerprints.

    python scripts/corpus_diff.py --save artifacts/corpus/<fingerprint>.json
    python scripts/corpus_diff.py --against artifacts/corpus/<fingerprint>.json

S6 asks for "corpus diff reports between fingerprints". `corpus_version()` already tells you
THAT the corpus changed — a single 12-hex value over every act's source sha256 and parsed
content. What it cannot tell you is WHAT changed, and that is the question that matters when a
re-ingest moves the fingerprint: did a parser flag recover forty provisions, or did it quietly
swallow four?

This reports per-act and per-section: acts added or removed, sections added or removed, and
sections whose TEXT changed, with the size delta. A re-ingest that loses provisions is then
visible as a list of section numbers rather than as one hex string that differs.

Deliberately compares the SHIPPED fulltext, not the parser, because that is what the vector
index is built from and what an advocate ultimately reads.

Exit codes:  0 = no differences (or snapshot saved) · 1 = differences found · 2 = usage error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FULLTEXT = REPO_ROOT / "app" / "legal_corpus" / "fulltext"


def snapshot() -> dict:
    """A compact, comparable view of the corpus: per act, per section, a text hash."""
    acts = {}
    for path in sorted(FULLTEXT.glob("*.fulltext.json")):
        for act in json.loads(path.read_text(encoding="utf-8")).get("acts", []):
            sections = {}
            for sec in act.get("sections", []):
                text = sec.get("text") or ""
                sections[str(sec["num"])] = {
                    "sha": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                    "len": len(text),
                    "title": (sec.get("title") or "")[:120],
                }
            acts[act["id"]] = {
                "title": act.get("title", ""),
                "status": act.get("status", ""),
                "source_sha256": (act.get("source") or {}).get("sha256", ""),
                "section_count": len(sections),
                "sections": sections,
            }
    return {"acts": acts}


def diff(old: dict, new: dict) -> list[str]:
    report: list[str] = []
    old_acts, new_acts = old.get("acts", {}), new.get("acts", {})

    for act_id in sorted(set(old_acts) - set(new_acts)):
        report.append(f"ACT REMOVED   {act_id}  ({old_acts[act_id]['section_count']} sections)")
    for act_id in sorted(set(new_acts) - set(old_acts)):
        report.append(f"ACT ADDED     {act_id}  ({new_acts[act_id]['section_count']} sections)")

    for act_id in sorted(set(old_acts) & set(new_acts)):
        o, n = old_acts[act_id], new_acts[act_id]
        if o["source_sha256"] != n["source_sha256"]:
            report.append(f"SOURCE CHANGED {act_id}  the upstream PDF is not the one ingested "
                          f"before — re-verify provenance")

        o_secs, n_secs = o["sections"], n["sections"]
        removed = sorted(set(o_secs) - set(n_secs))
        added = sorted(set(n_secs) - set(o_secs))
        if removed:
            report.append(f"SECTIONS LOST  {act_id}: {len(removed)} -> {', '.join(removed[:25])}"
                          + (" ..." if len(removed) > 25 else ""))
        if added:
            report.append(f"SECTIONS GAINED {act_id}: {len(added)} -> {', '.join(added[:25])}"
                          + (" ..." if len(added) > 25 else ""))

        for num in sorted(set(o_secs) & set(n_secs)):
            if o_secs[num]["sha"] != n_secs[num]["sha"]:
                delta = n_secs[num]["len"] - o_secs[num]["len"]
                report.append(
                    f"TEXT CHANGED   {act_id} s.{num}  {o_secs[num]['len']} -> "
                    f"{n_secs[num]['len']} chars ({delta:+d})")
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Diff the corpus against a saved snapshot.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", metavar="PATH", help="write a snapshot of the current corpus")
    g.add_argument("--against", metavar="PATH", help="diff the current corpus against a snapshot")
    ap.add_argument("--quiet", action="store_true", help="summary counts only")
    args = ap.parse_args(argv[1:])

    current = snapshot()

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        total = sum(a["section_count"] for a in current["acts"].values())
        print(f"snapshot written: {out}  ({len(current['acts'])} acts, {total} sections)")
        return 0

    src = Path(args.against)
    if not src.is_file():
        print(f"no such snapshot: {src}", file=sys.stderr)
        return 2

    report = diff(json.loads(src.read_text(encoding="utf-8")), current)
    if not report:
        print("No corpus differences.")
        return 0

    lost = sum(1 for line in report if line.startswith("SECTIONS LOST"))
    print(f"{len(report)} difference(s) against {src.name}:\n")
    if not args.quiet:
        for line in report:
            print("  " + line)
        print()
    kinds = {}
    for line in report:
        kinds[line.split()[0]] = kinds.get(line.split()[0], 0) + 1
    print("summary:", ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    if lost:
        print("\nSECTIONS WERE LOST. A re-ingest that removes provisions is a regression until "
              "proven otherwise — check each against the official source before shipping.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
