"""The committed corpus must have been built by the parser that is committed beside it.

THE GAP THIS CLOSES
-------------------
Every other corpus test reads the shipped JSON in `app/legal_corpus/fulltext/`. None re-runs
the parser. So the parser can change, the artifact can stay behind, and nothing fails — the
corpus on disk looks correct while the code that produces it no longer agrees.

On 2026-08-08 a full rebuild found Indian Succession Act ss.30 and 90 being DELETED by the
parser and absorbed into ss.29 and 89: `_FOOTNOTE_RE` drops lines opening with an editorial
word, and those two sections genuinely begin "As to what property deceased considered to have
died intestate.—" and "Words describing subject refer to…". The defect had been live since
those openers were added. The committed corpus predated the change, still held the correct
text, and the entire suite stayed green. It surfaced only because an unrelated fix forced a
rebuild.

WHY A HASH AND NOT A REBUILD
----------------------------
A real rebuild is the proper check and lives in `scripts/verify_corpus_rebuild.py`. It cannot
run in GitHub CI: it needs `data/source_pdfs/`, which is 154 MB, gitignored, and includes a
106 MB file that exceeds GitHub's per-file limit outright. Re-downloading is not an option
either — some sources are WAF-protected (see docs/CORPUS_LIMITATIONS.md).

So this test enforces the part CI *can* check, in milliseconds: the parser's hash still
matches the one recorded when the corpus was last rebuilt.

BE CLEAR ABOUT ITS LIMITS. Passing means the corpus was produced by a parser with this exact
hash. It does NOT mean the parse is correct, and it will not notice a source PDF being
replaced. Only a real rebuild shows that. This test's job is narrower and worth having: it
makes "someone changed the parser and forgot to rebuild" impossible to miss.

It is deliberately strict — ANY edit to the parser trips it, including a comment. That is the
honest position: you cannot know a change is semantically inert without rebuilding, and the
cost of being wrong here is law that is silently not the law.
"""
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PARSER = ROOT / "app" / "ai" / "ingest_statutes.py"
FINGERPRINT = ROOT / "PARSER_FINGERPRINT.json"


@pytest.fixture(scope="module")
def fingerprint() -> dict:
    assert FINGERPRINT.exists(), (
        f"{FINGERPRINT.relative_to(ROOT)} is missing. It records which parser built the "
        f"committed corpus. Regenerate with:\n"
        f"  python scripts/verify_corpus_rebuild.py --all --stamp")
    return json.loads(FINGERPRINT.read_text(encoding="utf-8"))


def test_the_corpus_was_built_by_the_committed_parser(fingerprint):
    actual = hashlib.sha256(PARSER.read_bytes()).hexdigest()
    recorded = fingerprint["parser_sha256"]
    assert actual == recorded, (
        "app/ai/ingest_statutes.py has changed since the corpus was last rebuilt.\n"
        f"  recorded: {recorded}\n"
        f"  current : {actual}\n\n"
        "The committed corpus may no longer be what this parser produces. That is exactly how\n"
        "Indian Succession ss.30 and 90 stayed lost while every test passed.\n\n"
        "On a machine that has data/source_pdfs/:\n"
        "  python scripts/verify_corpus_rebuild.py --all --stamp\n"
        "then reseed and re-freeze:\n"
        "  python -c \"from app.ai.vector_store import reseed; reseed()\"\n"
        "  python -m app.ops.release freeze\n\n"
        "If the change is genuinely cosmetic and you have confirmed by rebuilding that no act\n"
        "changed, re-stamping alone is enough.")


def test_the_fingerprint_covers_every_act(fingerprint):
    """A fingerprint recorded over a subset would assert more than it checked."""
    shipped = len(list((ROOT / "app" / "legal_corpus" / "fulltext").glob("*.fulltext.json")))
    assert fingerprint["act_count"] == shipped, (
        f"the fingerprint was stamped over {fingerprint['act_count']} acts but {shipped} are "
        f"shipped; re-stamp with --all")


def test_the_fingerprint_records_how_it_was_verified(fingerprint):
    """A stamp with no provenance is a rubber stamp."""
    assert fingerprint.get("verified_by", "").strip(), (
        "PARSER_FINGERPRINT.json has no `verified_by` — it must record what proved the corpus "
        "matches the parser, so a bootstrap stamp cannot be mistaken for a verified one")


def test_the_check_would_actually_fail(fingerprint):
    """Guards the guard: a hash comparison that cannot fail is decoration.

    Cheap, but this file exists BECAUSE a whole category of defect hid behind tests that
    could not fail. Prove this one can.
    """
    tampered = hashlib.sha256(PARSER.read_bytes() + b"\n# an edit\n").hexdigest()
    assert tampered != fingerprint["parser_sha256"], (
        "modifying the parser did not change its hash — the comparison is not measuring "
        "the file")
