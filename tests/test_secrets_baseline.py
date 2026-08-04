"""The secret-scanning baseline must be committed in a form the CI gate can read.

`.secrets.baseline` keys findings by file path, and detect-secrets writes them using the
**native** separator of whatever machine generated it. This project is developed on Windows
and gated on Linux, so a baseline regenerated locally is committed with `app\\models\\user.py`
while the CI runner looks up `app/models/user.py`. Every lookup misses, every finding reads as
new, and the BLOCKING secret scan fails on a clean tree.

That is not hypothetical — it happened on CI run #27, on the very commit that introduced the
scan. Both test lanes were green and the audit job went red, with 50 of 54 baseline keys
carrying backslashes. It passed locally beforehand precisely because the baseline and the
verification ran on the same Windows box: a gate checked only on the platform that produced
its data has not been checked.

Forward slashes are the canonical form — it is what git itself stores — so this asserts the
committed baseline uses them. Regenerating on Windows and committing without normalising now
fails here instead of in CI.

    Normalise after regenerating:
        python -c "import json,pathlib;p=pathlib.Path('.secrets.baseline');b=json.loads(p.read_text());b['results']={k.replace(chr(92),'/'):v for k,v in b['results'].items()};p.write_text(json.dumps(b,indent=2,sort_keys=True)+chr(10))"
"""
import json
import pathlib

BASELINE = pathlib.Path(__file__).resolve().parent.parent / ".secrets.baseline"


def _baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_baseline_exists():
    assert BASELINE.is_file(), (
        ".secrets.baseline is missing — the BLOCKING secret scan in CI has nothing to compare "
        "against and will fail")


def test_baseline_paths_use_posix_separators():
    """A Windows-generated baseline is unreadable by the Linux CI gate."""
    offenders = sorted(k for k in _baseline().get("results", {}) if "\\" in k)
    assert not offenders, (
        f"{len(offenders)} baseline entries use Windows path separators, e.g. "
        f"{offenders[0]!r}. The CI runner looks these up with forward slashes, so every one "
        f"reads as a NEW secret and the blocking scan fails on a clean tree. Normalise the "
        f"keys (see this module's docstring) before committing."
    )


def test_baseline_paths_point_at_files_that_exist():
    """Entries for deleted files are dead weight that hides real drift.

    Not fatal to the gate — detect-secrets ignores them — but a baseline half-full of stale
    paths stops being reviewable, and reviewability is the only reason to keep an allowlist
    rather than switching the scanner off.
    """
    root = BASELINE.parent
    missing = sorted(k for k in _baseline().get("results", {}) if not (root / k).is_file())
    assert not missing, (
        "the baseline lists files that no longer exist: " + ", ".join(missing[:10]))
