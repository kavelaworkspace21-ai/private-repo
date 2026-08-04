"""Turn a pytest JUnit XML report into GitHub Actions annotations.

Why this exists.

Diagnosing a red CI run has repeatedly meant scraping thousands of lines of rendered HTML
out of the Actions web UI in a browser, because the two machine-readable routes are both
shut:

  * the check-run **annotations** API returns only `Process completed with exit code 1`,
    since a failing `run:` step produces exactly one annotation and pytest emits none;
  * the **logs** and **artifact download** APIs require an authenticated token, so the JUnit
    XML this repo already uploads cannot be fetched without one (HTTP 401/403).

Annotations, unlike logs and artifacts, ARE readable unauthenticated on a public repository.
Emitting one per failing test therefore makes a failure diagnosable from the API alone —
test id, file, line and message — with no login and no log scraping.

It also makes the run page itself far more useful: failures appear at the top of the job and
inline on the offending line, instead of only in the middle of a 5,000-line log.

This never changes the build result. It runs only on failure and only reports what the XML
already says; the suite step's own exit code is what fails the job.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# GitHub renders a bounded number of annotations per step; past that they are dropped
# silently. Cap explicitly and say how many were withheld, so a truncated list is never
# mistaken for the whole story.
MAX_ANNOTATIONS = 20


def _one_line(text: str, limit: int = 300) -> str:
    """Collapse a multi-line failure message into a single annotation-safe line."""
    flat = " ".join((text or "").split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: annotate_junit.py <junit.xml> [label]", file=sys.stderr)
        return 2

    path = Path(argv[1])
    label = argv[2] if len(argv) > 2 else path.stem
    if not path.exists():
        # Not an error: the suite may have died before writing a report at all.
        print(f"::warning::{label}: no JUnit report at {path} — nothing to annotate")
        return 0

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        print(f"::warning::{label}: could not parse {path}: {exc}")
        return 0

    problems = []
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is None:
                continue
            problems.append({
                "kind": kind,
                "file": case.get("file") or "",
                "line": case.get("line") or "",
                "name": f"{case.get('classname', '')}::{case.get('name', '')}".strip(":"),
                "message": _one_line(node.get("message") or node.text or ""),
            })
            break

    if not problems:
        print(f"{label}: JUnit report lists no failures or errors.")
        return 0

    print(f"::group::{label}: {len(problems)} failing test(s)")
    for p in problems[:MAX_ANNOTATIONS]:
        # NOTE: pytest's default junit_family=xunit2 does NOT emit file/line attributes, so
        # in practice this produces a job-level annotation rather than an inline one. The
        # `classname` is fully qualified (tests.test_postgres_parity::test_name), which is
        # enough to identify the test. Handled anyway so that switching to xunit1, or another
        # producer, upgrades the annotation instead of breaking it.
        loc = f"file={p['file']}," if p["file"] else ""
        # JUnit line numbers are 0-based; GitHub annotations are 1-based.
        if p["line"].isdigit():
            loc += f"line={int(p['line']) + 1},"
        print(f"::error {loc}title={label}: {p['name']}::{p['message']}")

    withheld = len(problems) - MAX_ANNOTATIONS
    if withheld > 0:
        print(f"::error title={label}::…and {withheld} further failure(s) not annotated; "
              f"see the {label} JUnit artifact for the complete list.")
    print("::endgroup::")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
