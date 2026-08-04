"""Run detect-secrets against the baseline and report findings as GitHub annotations.

Why this wrapper exists rather than calling `detect-secrets-hook` directly:

The raw hook prints its findings to the job LOG, and the log requires an authenticated token
to read — as does artifact download. The check-run **annotations** API does not. So when the
blocking secret scan failed on CI runs #27 and #28, the only thing visible from outside was
`Process completed with exit code 1`, and diagnosing it meant guessing. Twice.

Emitting one annotation per finding makes a red secret scan diagnosable from a single
unauthenticated API call — the same reasoning as `.github/scripts/annotate_junit.py`, applied
to the job that actually needed it.

It changes no outcome: the exit code is the hook's own.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / ".secrets.baseline"
MAX_ANNOTATIONS = 25


def _exclude_pattern() -> re.Pattern | None:
    """The baseline's OWN exclusion regex, so there is one source of truth.

    `detect-secrets scan` applies the `should_exclude_file` filter recorded in the baseline
    when it walks the tree. `detect-secrets-hook` does NOT when files are passed explicitly —
    it scans exactly what it is given. Handing it `git ls-files` therefore scans things the
    baseline was never built to cover (generated artifacts, vendored JS, lockfiles), and every
    hit in them is reported as a new secret.
    """
    import json
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    for f in baseline.get("filters_used", []):
        if f.get("path", "").endswith("should_exclude_file"):
            pattern = f.get("pattern")
            if isinstance(pattern, list):
                pattern = pattern[0] if pattern else None
            if pattern:
                return re.compile(pattern)
    return None


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT,
                         capture_output=True, text=True, check=True).stdout
    files = [line for line in out.splitlines() if line.strip()]

    # The baseline must never be scanned against itself. It stores `hashed_secret` values,
    # which are by construction high-entropy strings, so scanning it reports dozens of
    # "secrets" that are the records OF secrets. `detect-secrets scan` excludes it
    # automatically; the hook does not when handed an explicit file list.
    files = [f for f in files if Path(f).name != BASELINE.name]

    exclude = _exclude_pattern()
    if exclude is not None:
        files = [f for f in files if not exclude.search(f)]
    return files


def _native_baseline(tmpdir: str) -> str:
    """A copy of the baseline keyed with THIS platform's path separator.

    detect-secrets keys findings by path using the native separator, so a baseline generated
    on Windows (`app\\models\\user.py`) does not match a scan on Linux (`app/models/user.py`)
    and vice versa — every lookup misses and a clean tree fails the gate. That was CI runs #27
    and #28.

    The committed baseline stays canonical POSIX, which is what git itself stores and what the
    Linux gate needs; this converts in memory at scan time so the same file works on both. The
    alternative — committing whichever separator the last developer's machine happened to
    use — makes the gate platform-locked and silently wrong on the other one.
    """
    import json
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline["results"] = {
        k.replace("/", os.sep).replace("\\", os.sep): v
        for k, v in baseline.get("results", {}).items()
    }
    path = Path(tmpdir) / ".secrets.baseline"
    path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    return str(path)


def main() -> int:
    if not BASELINE.is_file():
        print(f"::error title=Secret scan::{BASELINE.name} is missing — the gate has nothing "
              f"to compare against")
        return 1

    files = _tracked_files()
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, "-m", "detect_secrets.pre_commit_hook", "--baseline",
             _native_baseline(tmp), *files],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        output = (proc.stdout or "") + (proc.returncode and (proc.stderr or "") or "")
    print(output)

    if proc.returncode == 0:
        print(f"Secret scan clean: {len(files)} tracked files checked against the baseline.")
        return 0

    # detect-secrets prints blocks of "Secret Type: X" / "Location:    path:line".
    types = re.findall(r"^Secret Type:\s*(.+)$", output, re.MULTILINE)
    locs = re.findall(r"^Location:\s*(.+)$", output, re.MULTILINE)
    findings = list(zip(types, locs))

    print(f"::group::Secret scan: {len(findings)} finding(s) not in the baseline")
    if not findings:
        # No parseable findings — surface the raw tail so the failure is never silent.
        tail = " ".join(output.split())[-600:]
        print(f"::error title=Secret scan::exit {proc.returncode}, no parseable findings. "
              f"Output tail: {tail}")
    for secret_type, location in findings[:MAX_ANNOTATIONS]:
        # The LOCATION is the diagnostic — it is the file path, and a path-separator or
        # baseline-staleness problem shows up here immediately.
        print(f"::error title=Secret scan: {secret_type.strip()}::"
              f"{location.strip()} is not in .secrets.baseline")
    if len(findings) > MAX_ANNOTATIONS:
        print(f"::error title=Secret scan::…and {len(findings) - MAX_ANNOTATIONS} more")
    print("::endgroup::")

    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
