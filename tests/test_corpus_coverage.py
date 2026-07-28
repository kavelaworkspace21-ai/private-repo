"""Corpus coverage: landmark provisions must be present, and known gaps must stay honest.

Found 2026-07-24 while authoring the Phase 3 evaluation set: the deterministic parser
silently DROPPED provisions that are plainly present in the source PDFs. Three were
confirmed by extracting the PDF text and comparing:

    Indian Contract Act s.73        compensation for breach of contract
    Specific Relief Act s.10        specific performance
    Transfer of Property Act s.53A  part performance

These are not obscure. s.73 is the provision behind most contract damages claims. The acts
carry `source_verified: True`, and landmark verification passed — because it checked
different sections. That is the real lesson: content verification only proves what it
samples.

This file does two jobs:
  1. MUST_BE_PRESENT — a regression guard so the provisions we rely on cannot vanish again.
  2. KNOWN_MISSING — the confirmed defects, asserted to still be missing, so the list
     cannot quietly outlive the bug. When the parser is fixed and the act re-ingested,
     this test fails and tells you to delete the entry.
"""
import json
import pathlib

import pytest

FULL = pathlib.Path(__file__).resolve().parent.parent / "app" / "legal_corpus" / "fulltext"


def _sections(stem: str) -> set[str]:
    act = json.loads((FULL / f"{stem}.fulltext.json").read_text(encoding="utf-8"))["acts"][0]
    return {str(s.get("num")) for s in act["sections"]}


def _section(stem: str, num: str) -> dict | None:
    act = json.loads((FULL / f"{stem}.fulltext.json").read_text(encoding="utf-8"))["acts"][0]
    for s in act["sections"]:
        if str(s.get("num")) == num:
            return s
    return None


# Provisions an Indian advocate will reach for constantly. If any of these disappears, the
# product is quietly broken for a whole category of question.
MUST_BE_PRESENT = [
    ("negotiable_instruments_1881", "138", "cheque dishonour"),
    ("ipc_1860", "302", "murder"),
    ("ipc_1860", "420", "cheating"),
    ("constitution_1950", "21", "life and personal liberty"),
    ("constitution_1950", "32", "constitutional remedies"),
    ("crpc_1973", "438", "anticipatory bail"),
    ("cpc_1908", "151", "inherent powers"),
    ("cpc_1908", "9", "civil court jurisdiction"),
    ("ndps_1985", "37", "bail restrictions"),
    ("limitation_1963", "5", "condonation of delay"),
    ("contract_1872", "10", "what agreements are contracts"),
    ("dpdp_2023", "8", "data fiduciary obligations"),
    ("consumer_protection_2019", "35", "manner of complaint"),
    ("cgst_2017", "16", "input tax credit"),
    # Recovered 2026-07-25 — these are the provisions the parser had silently dropped.
    ("contract_1872", "73", "compensation for breach of contract"),
    ("specific_relief_1963", "10", "specific performance"),
    ("transfer_of_property_1882", "53A", "part performance"),
]

# CONFIRMED dropped by the parser — present in the source PDF, absent from the corpus.
# All three were RECOVERED on 2026-07-25 (parser fix + targeted re-ingest) and are now
# asserted present in MUST_BE_PRESENT above. The list stays, empty, because the class of
# defect has not gone away: docs/CORPUS_LIMITATIONS.md records that five suspect acts are
# still unprobed.
KNOWN_MISSING: list[tuple[str, str, str]] = []


@pytest.mark.parametrize("stem,num,label", MUST_BE_PRESENT,
                         ids=[f"{s}-{n}" for s, n, _ in MUST_BE_PRESENT])
def test_landmark_provision_is_in_the_corpus(stem, num, label):
    sec = _section(stem, num)
    assert sec is not None, (
        f"{stem} s.{num} ({label}) is missing from the corpus — retrieval for this topic "
        "will fall back to semantic search and may ground on the wrong provision")
    # Presence of the NUMBER is not enough: the original bug produced heading-only entries
    # while the body was captured under the previous section. Require real body text so a
    # section cannot pass this check as an empty shell.
    body = (sec.get("text") or "").strip()
    assert len(body) >= 40, (
        f"{stem} s.{num} ({label}) is present but its body is empty/stub ({len(body)} chars) "
        "— the provision text was not captured")


def test_known_parser_gaps_are_still_gaps():
    """Keeps the defect list truthful.

    If a re-ingest fixes one of these, this fails so the entry gets removed rather than
    silently misrepresenting the corpus as worse than it is.
    """
    fixed = [(s, n, why) for s, n, why in KNOWN_MISSING if n in _sections(s)]
    assert not fixed, (
        f"these are no longer missing — remove them from KNOWN_MISSING: {fixed}")


def test_the_corpus_still_covers_fifty_acts():
    files = sorted(FULL.glob("*.json"))
    assert len(files) == 50, f"expected 50 acts, found {len(files)}"


# ── TOC poisoning guard ─────────────────────────────────────────────────────────
def test_no_act_is_parsed_from_its_table_of_contents():
    """An act's provisions must be BODY text, not Arrangement-of-Sections headings.

    Found 2026-07-25: the entire committed Income-tax Act 1961 corpus was the table of
    contents. 791 "provisions" with a median of 46 characters, every page number inside
    1-29 of an 880-page PDF. s.2 (Definitions) was 12 characters from page 1; the real
    provision is 62,740 characters on page 30. s.139 (Return of income) was 17 characters
    against a real 24,495.

    The act carried source_verified: True and its text was quotable as authority, so the
    assistant could present a bare heading as the operative statutory provision.

    The parser already had a TOC-skip chooser (see test_ingest_parser's C-01b); the corpus
    file simply predated it and was never regenerated. Nothing compared the two, because the
    fingerprint hashes the committed file and stays stable while the parser moves on.

    A median under ~120 characters means the file is a list of headings, not law.
    """
    import statistics

    poisoned = []
    for path in sorted(FULL.glob("*.json")):
        act = json.loads(path.read_text(encoding="utf-8"))["acts"][0]
        lengths = [len((s.get("text") or "").strip()) for s in act["sections"]]
        if not lengths:
            continue
        median = statistics.median(lengths)
        if median < 120:
            poisoned.append((act["id"], len(lengths), int(median)))

    assert not poisoned, (
        "these acts look parsed from their table of contents rather than their body "
        f"(id, sections, median chars): {poisoned}")


def test_income_tax_1961_has_real_provision_text():
    """Explicit regression for the act that was poisoned — by content, not by count."""
    for num, minimum in (("2", 10_000), ("139", 5_000)):
        sec = _section("income_tax_1961", num)
        assert sec is not None, f"income_tax_1961 s.{num} missing"
        assert len(sec["text"]) >= minimum, (
            f"s.{num} is {len(sec['text'])} chars — that is a heading, not the provision")
        assert (sec.get("page") or 0) > 29, (
            f"s.{num} came from page {sec.get('page')}, inside the table-of-contents range")


def test_repealed_acts_name_their_successor():
    """A repeal banner that cannot say what replaced the Act is half an answer.

    Found 2026-07-25: `repealed_by` and the transitional note lived in the committed
    income_tax_1961 JSON but NOT in the registry that regenerates it, so a re-ingest
    silently blanked them and the banner stopped naming the Income-tax Act, 2025.

    That is the same artifact/generator drift that left the same act parsed from its table
    of contents — only reversed: there the artifact was WORSE than the code could rebuild,
    here it was RICHER. Both mean the corpus and its generator disagree, and nothing
    compared them. This asserts the property on the artifact; the fix belongs in the
    registry, never by hand-patching the JSON.
    """
    missing = []
    for path in sorted(FULL.glob("*.json")):
        act = json.loads(path.read_text(encoding="utf-8"))["acts"][0]
        if act.get("status") == "repealed" and not (act.get("repealed_by") or "").strip():
            missing.append(act["id"])
    assert not missing, (
        f"repealed acts with no successor recorded (add `repealed_by` to STATUTE_REGISTRY, "
        f"then re-ingest): {missing}")
