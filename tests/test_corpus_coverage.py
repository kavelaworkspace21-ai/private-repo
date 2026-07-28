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
