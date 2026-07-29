"""Corpus integrity — amending text must never occupy a principal Act's section.

India Code prints the amending Act after the principal Act in the same PDF. Its clauses
renumber from 1 ("16. In section 31 of the principal Act,—"), so without a boundary they
parse as sections and COLLIDE with the principal Act's numbering. The genuine provision is
replaced by an amendment stub, and nothing announces it: the section exists, has plausible
length, and retrieves fine. It just isn't the law.

Found 2026-07-30, present since before version control. Ten sections across three acts held
amendment text instead of provisions — including arbitration s.16 (competence of the
arbitral tribunal to rule on its own jurisdiction), CrPC s.16 (Courts of Metropolitan
Magistrates), s.44 (Arrest by Magistrate) and IBC s.6 (who may initiate a corporate
insolvency resolution process).

This test scans the SHIPPED corpus, not the parser, because that is where the damage was
visible and where nobody was looking. All ten are fixed, by two different boundary
rules: `drop_extracts_appendix` for appended amendment Acts (arbitration, CrPC) and
`body_before_schedule` for Schedules that amend OTHER enactments (IBC's Eleventh Schedule
rewrites the Companies Act). The expected count is zero, and any new contamination fails
the suite immediately.
"""
import json
import pathlib
import re

FULLTEXT = pathlib.Path(__file__).parent.parent / "app" / "legal_corpus" / "fulltext"

# Openings that only ever occur in AMENDING legislation, never in a principal provision.
AMENDING_TEXT = re.compile(
    r"(In section \d+[A-Z]* of the principal Act"
    r"|of the principal Act,"
    r"|shall be (?:substituted|omitted|inserted)\b.{0,40}(?:namely|principal Act))",
    re.I,
)

# EMPTY, and it must stay that way. All ten contaminated sections are fixed:
# `drop_extracts_appendix` handled arbitration and CrPC (appended amendment Acts), and
# `body_before_schedule` handled IBC (Schedules that amend OTHER enactments — the Eleventh
# Schedule rewrites the Companies Act). Anything appearing here is a new defect, not a
# tolerated one.
KNOWN_CONTAMINATED: set[tuple[str, str]] = set()


def _contaminated():
    found = set()
    for f in sorted(FULLTEXT.glob("*.fulltext.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for act in data.get("acts", []):
            for sec in act.get("sections", []):
                text = re.sub(r"\s+", " ", sec.get("text", "") or "")
                # Only the OPENING matters: a provision may legitimately mention amendments
                # further in, but a section that BEGINS this way is the amending clause.
                if AMENDING_TEXT.search(text[:200]):
                    found.add((act["id"], str(sec["num"])))
    return found


def test_no_new_amendment_text_masquerading_as_a_provision():
    """The guard that would have caught this on day one."""
    found = _contaminated()
    new = found - KNOWN_CONTAMINATED
    assert not new, (
        "Sections whose text is AMENDING legislation, not the provision itself:\n  "
        + "\n  ".join(f"{a} s.{n}" for a, n in sorted(new))
        + "\nAn appended amendment Act is being segmented into the principal Act. See "
          "_extracts_appendix_page() / the `drop_extracts_appendix` registry flag."
    )


def test_the_corpus_is_entirely_clean():
    """No tolerated exceptions. All ten known cases are fixed; keep it at zero."""
    assert _contaminated() == set(), (
        "The corpus is supposed to be free of amending text masquerading as provisions. "
        "If a new act legitimately cannot be cleaned, add it to KNOWN_CONTAMINATED with a "
        "recorded reason — do not delete this test.")


def test_the_detector_actually_detects():
    """A scanner that finds nothing because its pattern is broken is worse than none."""
    sample = ("In section 31 of the principal Act,— Amendment of section 31. "
              "(i) in sub-section (1), the following shall be substituted")
    assert AMENDING_TEXT.search(sample), "pattern must match real amending-clause text"
    provision = ("Competence of arbitral tribunal to rule on its jurisdiction.—(1) The "
                 "arbitral tribunal may rule on its own jurisdiction, including ruling on "
                 "any objections with respect to the existence or validity of the "
                 "arbitration agreement.")
    assert not AMENDING_TEXT.search(provision[:200]), "must not flag a genuine provision"


def test_restored_provisions_are_actually_the_provisions():
    """Spot-check the six sections the boundary fix recovered."""
    expected = {
        ("ibc_2016", "6"): "persons who may initiate",
        ("ibc_2016", "19"): "personnel to extend cooperation",
        ("ibc_2016", "36"): "liquidation estate",
        ("arbitration_1996", "16"): "competence of arbitral tribunal",
        ("arbitration_1996", "6"): "administrative assistance",
        ("arbitration_1996", "18"): "equal treatment of parties",
        ("crpc_1973", "16"): "courts of metropolitan magistrates",
        ("crpc_1973", "38"): "aid to person",
        ("crpc_1973", "44"): "arrest by magistrate",
    }
    for (act_id, num), opening in expected.items():
        path = FULLTEXT / f"{act_id}.fulltext.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        secs = {str(s["num"]): s.get("text", "") for s in data["acts"][0]["sections"]}
        assert num in secs, f"{act_id} s.{num} missing"
        assert secs[num][:80].lower().startswith(opening), (
            f"{act_id} s.{num} should open with {opening!r}, got {secs[num][:80]!r}")
