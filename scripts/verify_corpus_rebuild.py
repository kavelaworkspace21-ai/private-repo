"""Re-derive the corpus from the source PDFs and prove it matches what is committed.

WHY THIS EXISTS
---------------
Every other corpus test in this repository reads the SHIPPED JSON in
`app/legal_corpus/fulltext/`. None of them re-runs the parser. That leaves a gap with a
specific shape: the parser can change, the committed artifact can stay behind, and the two
drift apart with nothing failing — the artifact on disk looks correct while the code that
produces it no longer agrees.

That is not hypothetical. On 2026-08-08 a full rebuild revealed that Indian Succession Act
ss.30 and 90 were being DELETED by the parser and absorbed into ss.29 and 89. `_FOOTNOTE_RE`
drops lines whose first word after the number is an editorial opener (`Subs.`, `Ins.`,
`As to`, `Words`), and those two sections genuinely open "As to what property deceased
considered to have died intestate.—" and "Words describing subject refer to…". The defect had
been live since those openers were added. The committed corpus predated the change and was
never rebuilt, so it still held the correct text, and the whole suite stayed green.

It surfaced only because an unrelated `_START_RE` fix happened to force a full rebuild. This
script removes the "happened to" from that sentence.

WHAT IT CHECKS
--------------
For each act: re-ingest from `data/source_pdfs/`, then compare the result against the
committed fulltext, provision by provision — number, title, text and source page. Any
addition, removal or altered text is a failure, because either the artifact is stale or the
parser has regressed, and both need a human to say which.

`fetched_on` is deliberately ignored. Ingest stamps it with today's date, so it differs on
every run and says nothing about whether the parse is correct.

USAGE
-----
    python scripts/verify_corpus_rebuild.py --skip-slow          # every act but income_tax_2025
    python scripts/verify_corpus_rebuild.py --shard 0 --of 4     # one CI shard
    python scripts/verify_corpus_rebuild.py --acts cpc_1908,ndps_1985
    python scripts/verify_corpus_rebuild.py --all                # everything (~2 hours)

The rebuild WRITES to the fulltext directory, so the original files are restored on exit
unless `--no-restore` is passed. Without that, a developer running this locally would be left
with a working tree full of modified corpus files whose only real change is a date stamp.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai import ingest_statutes as ing  # noqa: E402

# income_tax_2025's source PDF is 106 MB — two orders of magnitude larger than a typical bare
# act — and it alone takes 75-95 minutes to parse, roughly three quarters of a full rebuild.
# Sharding cannot help: it is one indivisible act. So the fast lane skips it and the scheduled
# full lane covers it. Named here rather than buried in the workflow so the exclusion is
# visible to anyone reading the script.
SLOW_ACTS = {"income_tax_2025"}

# Metadata that legitimately differs on every run and says nothing about parse correctness.
VOLATILE_FIELDS = {"fetched_on"}


# The full rebuild needs the source PDFs, and they are NOT in the repository: 154 MB across
# 51 files, gitignored, and income_tax_2025.pdf alone is 106 MB — past GitHub's 100 MB
# per-file limit, so it cannot be committed even if that were desirable. A GitHub-hosted
# runner therefore cannot run this script at all.
#
# So the drift protection is split in two. This script is the real check and runs wherever the
# PDFs live. The fingerprint below is the part CI *can* enforce: it records which parser built
# the committed corpus, so a parser change that lands without a rebuild fails in seconds
# instead of waiting for someone to notice.
#
# Be clear about what the fingerprint does and does not prove. It proves the corpus was
# produced by a parser with this exact hash. It does NOT prove the parse is correct, and it
# does not notice a source PDF being replaced. Only a real rebuild does that.
#
# It lives at the repo ROOT, next to RELEASE.json — the other piece of pinned release
# identity — and deliberately NOT in app/legal_corpus/. That directory is DATA: library.py
# does `CORPUS_DIR.glob("*.json")` and reads every file there as an act index. The first
# draft put the fingerprint there with an `acts: 50` field, so the loader ran
# `for a in data.get("acts", [])` over an integer and took out ten library-search tests.
FINGERPRINT_PATH = ROOT / "PARSER_FINGERPRINT.json"
PARSER_PATH = ROOT / "app" / "ai" / "ingest_statutes.py"


def parser_sha256() -> str:
    """sha256 of the parser with line endings normalised to LF.

    NOT the raw bytes. This repo is developed on Windows with core.autocrlf=true, so the
    working copy has CRLF while the git blob — and therefore every Linux CI checkout — has LF.
    Hashing raw bytes produced two different fingerprints for the same file and failed all
    three CI jobs on a stamp made locally. A fingerprint that depends on which platform
    checked the file out is not an invariant at all.
    """
    import hashlib
    return hashlib.sha256(PARSER_PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
def write_fingerprint(note: str) -> dict:
    import datetime
    data = {
        "parser_path": "app/ai/ingest_statutes.py",
        "parser_sha256": parser_sha256(),
        "stamped_on": datetime.date.today().isoformat(),
        "act_count": len(act_ids()),
        "verified_by": note,
        "note": ("Which parser built the committed corpus. tests/test_corpus_freshness.py "
                 "fails if app/ai/ingest_statutes.py no longer hashes to this, which means a "
                 "parser change landed without the corpus being rebuilt. Re-stamp only after "
                 "running scripts/verify_corpus_rebuild.py --all on a machine that has "
                 "data/source_pdfs/."),
    }
    FINGERPRINT_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def act_ids() -> list[str]:
    """Every act with both a registry entry and a committed fulltext file."""
    return sorted(
        a for a in ing.STATUTE_REGISTRY
        if (ing.FULLTEXT_DIR / f"{a}.fulltext.json").exists()
    )


def _provisions(doc: dict) -> dict[str, dict]:
    out = {}
    for act in doc.get("acts", []):
        for sec in act.get("sections", []):
            out[str(sec["num"])] = {
                "text": sec.get("text", ""),
                "title": sec.get("title", ""),
                "page": sec.get("page"),
            }
    return out


def _scrub(value):
    """Drop volatile keys at any depth.

    `fetched_on` is nested inside `source`, not at the act's top level, so a shallow filter
    silently leaves it in and every act reports a metadata difference on every run — a check
    that always fails teaches people to ignore it, which is worse than not having it.
    """
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if k not in VOLATILE_FIELDS}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _meta(doc: dict) -> dict:
    """Act-level metadata, minus the fields that change on every run."""
    return {act.get("id", "?"): _scrub({k: v for k, v in act.items() if k != "sections"})
            for act in doc.get("acts", [])}


def compare(act_id: str, committed: dict, rebuilt: dict) -> list[str]:
    """Human-readable differences. Empty list means the rebuild reproduced the artifact."""
    problems: list[str] = []
    old, new = _provisions(committed), _provisions(rebuilt)

    for num in sorted(set(old) - set(new)):
        problems.append(
            f"  LOST     {act_id} {num}: in the committed corpus, NOT produced by the parser"
            f" — {old[num]['text'][:90]!r}")
    for num in sorted(set(new) - set(old)):
        problems.append(
            f"  NEW      {act_id} {num}: produced by the parser, NOT in the committed corpus"
            f" — {new[num]['text'][:90]!r}")
    for num in sorted(set(old) & set(new)):
        if old[num]["text"] != new[num]["text"]:
            problems.append(
                f"  CHANGED  {act_id} {num}: text differs "
                f"({len(old[num]['text'])} -> {len(new[num]['text'])} chars)")
        elif old[num]["page"] != new[num]["page"]:
            problems.append(
                f"  MOVED    {act_id} {num}: source page {old[num]['page']} -> "
                f"{new[num]['page']} (a citation would point at the wrong page)")

    if _meta(committed) != _meta(rebuilt):
        problems.append(f"  META     {act_id}: act-level metadata differs")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--acts", help="comma-separated act ids")
    p.add_argument("--shard", type=int, help="0-based shard index")
    p.add_argument("--of", type=int, help="total number of shards")
    p.add_argument("--all", action="store_true", help="include the slow acts")
    p.add_argument("--skip-slow", action="store_true",
                   help=f"exclude {', '.join(sorted(SLOW_ACTS))}")
    p.add_argument("--no-restore", action="store_true",
                   help="leave the rebuilt files in place (CI runners are ephemeral)")
    p.add_argument("--stamp", action="store_true",
                   help="on success, record the current parser hash in PARSER_FINGERPRINT.json")
    p.add_argument("--force-stamp", metavar="REASON",
                   help="write the fingerprint WITHOUT verifying. Only for bootstrapping, and "
                        "the reason is recorded in the file.")
    args = p.parse_args(argv)

    if args.force_stamp:
        data = write_fingerprint(args.force_stamp)
        print(f"Stamped WITHOUT verification: parser {data['parser_sha256'][:12]}")
        print(f"  reason recorded: {args.force_stamp}")
        return 0

    if args.acts:
        targets = [a.strip() for a in args.acts.split(",") if a.strip()]
    else:
        targets = act_ids()
        if args.skip_slow and not args.all:
            targets = [a for a in targets if a not in SLOW_ACTS]
        if args.shard is not None and args.of:
            targets = [a for i, a in enumerate(targets) if i % args.of == args.shard]

    if not targets:
        print("no acts selected", file=sys.stderr)
        return 2

    label = f"shard {args.shard}/{args.of}" if args.shard is not None else "all selected"
    print(f"Re-deriving {len(targets)} act(s) from source PDFs ({label})\n", flush=True)

    originals: dict[str, str] = {}
    problems: list[str] = []
    failed_to_parse: list[str] = []
    t0 = time.time()

    def restore() -> None:
        for act, text in originals.items():
            (ing.FULLTEXT_DIR / f"{act}.fulltext.json").write_text(text, encoding="utf-8")

    # A full run takes about two hours, so it WILL be interrupted — by Ctrl-C, by a CI
    # timeout, by a runner being reclaimed. `finally` does not run on SIGTERM, and a partial
    # run that leaves rebuilt files behind is worse than useless: the working tree then holds
    # a corpus nobody verified, differing from the committed one only by a date stamp, which
    # is exactly the sort of thing that gets committed by accident.
    #
    # Found the hard way: a 10-minute timeout killed a shard mid-run and left five acts
    # modified in the working tree.
    if not args.no_restore:
        import signal

        def _on_signal(signum, _frame):
            print(f"\ninterrupted (signal {signum}) — restoring {len(originals)} corpus file(s)",
                  flush=True)
            restore()
            sys.exit(130)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _on_signal)
            except (ValueError, OSError):
                pass          # not on the main thread, or unsupported on this platform

    try:
        for n, act_id in enumerate(targets, 1):
            path = ing.FULLTEXT_DIR / f"{act_id}.fulltext.json"
            originals[act_id] = path.read_text(encoding="utf-8")
            committed = json.loads(originals[act_id])

            started = time.time()
            try:
                ing.ingest(act_id)
            except Exception as exc:                      # noqa: BLE001 — report, don't abort
                failed_to_parse.append(f"  ERROR    {act_id}: {type(exc).__name__}: {exc}")
                print(f"  [{n}/{len(targets)}] {act_id} FAILED TO PARSE", flush=True)
                continue

            rebuilt = json.loads(path.read_text(encoding="utf-8"))
            diffs = compare(act_id, committed, rebuilt)
            problems.extend(diffs)
            mark = "OK " if not diffs else "DIFF"
            print(f"  [{n}/{len(targets)}] {mark} {act_id} ({time.time() - started:.0f}s)",
                  flush=True)
    finally:
        if not args.no_restore:
            restore()

    print(f"\nfinished in {time.time() - t0:.0f}s")

    if failed_to_parse:
        print("\nActs that could not be parsed at all:")
        print("\n".join(failed_to_parse))
    if problems:
        print(f"\n{len(problems)} difference(s) between the committed corpus and a fresh parse:")
        print("\n".join(problems[:60]))
        if len(problems) > 60:
            print(f"  … and {len(problems) - 60} more")
        print(
            "\nThe committed corpus and the parser disagree. Either the parser regressed, or a\n"
            "parser fix landed without the corpus being rebuilt — the second is how Indian\n"
            "Succession ss.30 and 90 stayed lost while every test passed.\n"
            "\nDecide which, then either fix the parser or rebuild and re-freeze:\n"
            "  python -m app.ai.ingest_statutes <act_id>      # rebuild one act\n"
            "  python -c \"from app.ai.vector_store import reseed; reseed()\"\n"
            "  python -m app.ops.release freeze")
    if problems or failed_to_parse:
        return 1

    print("The committed corpus is exactly what the parser produces from the source PDFs.")
    if args.stamp:
        if len(targets) < len(act_ids()):
            print(f"\nNOT stamping: only {len(targets)} of {len(act_ids())} acts were checked. "
                  "The fingerprint asserts the WHOLE corpus matches, so stamp only after "
                  "--all.")
            return 1
        data = write_fingerprint(f"full rebuild + diff, {data_today()}")
        print(f"Stamped: parser {data['parser_sha256'][:12]} over {data['act_count']} acts")
    return 0


def data_today() -> str:
    import datetime
    return datetime.date.today().isoformat()


if __name__ == "__main__":
    sys.exit(main())
