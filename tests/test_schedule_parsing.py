"""Schedules must be retrievable, and must never occupy a section number.

Schedules decide real outcomes. The Specific Relief schedule defines "infrastructure
project" for s.20A, which BARS injunctions against such projects. The NDPS schedule is the
list of what is controlled at all. Partnership Schedule I sets the registration fees.

They used to be dropped, or worse MISFILED. Schedule entries renumber from 1, so without a
namespace they collide with real section numbers and overwrite them — the collision that
cost ten sections of law across arbitration, CrPC and IBC, unnoticed since before version
control.

Two properties are load-bearing here, and both are asserted against the SHIPPED corpus
rather than a fresh parse, because a fresh parse is what concealed that damage:

  1. adding schedules changes NO body section, and
  2. no id appears twice — a duplicate id aborted the seed and silently dropped 12 acts on
     2026-07-12 (see the de-dup note in vector_store._seed_collection).
"""
import collections
import json
import pathlib
import re

import pytest

from app.ai import ingest_statutes as ing

FULLTEXT = pathlib.Path(__file__).parent.parent / "app" / "legal_corpus" / "fulltext"
SCHEDULED_ACTS = ["ndps_1985", "specific_relief_1963", "partnership_1932", "mediation_2023"]


def _sections(stem):
    data = json.loads((FULLTEXT / f"{stem}.fulltext.json").read_text(encoding="utf-8"))
    return data["acts"][0]["sections"]


def _norm(t):
    return re.sub(r"\s+", " ", t or "").strip()


@pytest.mark.parametrize("stem", SCHEDULED_ACTS)
def test_schedule_entries_exist_and_are_namespaced(stem):
    nums = [str(s["num"]) for s in _sections(stem)]
    sched = [n for n in nums if n.startswith("Sch")]
    assert sched, f"{stem} should carry schedule entries"
    for n in sched:
        assert re.fullmatch(r"Sch(\.[A-Z0-9IVX]+)+", n), f"malformed schedule id {n!r}"


@pytest.mark.parametrize("stem", SCHEDULED_ACTS)
def test_no_schedule_entry_shadows_a_section_number(stem):
    """The whole point of the namespace. A bare "17" from a schedule would clobber s.17."""
    nums = [str(s["num"]) for s in _sections(stem)]
    body = {n for n in nums if not n.startswith("Sch")}
    sched = [n for n in nums if n.startswith("Sch")]
    assert sched and body, "fixture needs both kinds"
    assert not (set(sched) & body), "a schedule id must never equal a section number"
    # The entry TAILS deliberately do repeat section numbers (schedules count from 1) —
    # that is precisely why the prefix exists, and why this must be checked rather than
    # assumed. Prove at least one such collision is neutralised by the namespace.
    tails = {n.split(".")[-1] for n in sched}
    assert tails & body, (
        "expected some schedule entry number to coincide with a real section number; if "
        "none do, this test is not exercising the protection it claims to")


@pytest.mark.parametrize("stem", SCHEDULED_ACTS)
def test_ids_are_unique(stem):
    nums = [str(s["num"]) for s in _sections(stem)]
    dupes = [n for n, c in collections.Counter(nums).items() if c > 1]
    assert not dupes, (
        f"duplicate ids in {stem}: {dupes}. ChromaDB rejects a batch containing one, which "
        f"aborts the seed and drops every act sorting after it.")


def test_specific_relief_schedule_defines_infrastructure_categories():
    """s.20A bars injunctions for "infrastructure projects" — defined only here."""
    secs = {str(s["num"]): _norm(s["text"]) for s in _sections("specific_relief_1963")}
    joined = " ".join(v for k, v in secs.items() if k.startswith("Sch")).lower()
    for expected in ("transport", "energy", "water", "communication", "social"):
        assert expected in joined, f"infrastructure category {expected!r} missing"
    assert "20a" in " ".join(secs).lower() or "20A" in secs, "s.20A itself must still exist"


def test_ndps_schedule_lists_controlled_substances():
    secs = {str(s["num"]): _norm(s["text"]) for k, s in
            ((str(s["num"]), s) for s in _sections("ndps_1985"))}
    sched = {k: v for k, v in secs.items() if k.startswith("Sch")}
    assert len(sched) > 50, "the psychotropic list should be long"
    joined = " ".join(sched.values()).lower()
    for substance in ("lysergide", "mescaline", "psilocybine"):
        assert substance in joined, f"{substance} missing from the controlled list"


def test_partnership_schedule_carries_the_registration_fees():
    sched = [_norm(s["text"]) for s in _sections("partnership_1932")
             if str(s["num"]).startswith("Sch")]
    joined = " ".join(sched).lower()
    assert "statement under section 58" in joined
    assert "rupees" in joined


# ── unit-level behaviour of the segmenter ───────────────────────────────────────
def _page(lines):
    return "\n".join(lines)


def test_prose_mentioning_a_schedule_is_not_treated_as_a_heading():
    """The SRA says "the Schedule relating to any Category" mid-sentence in s.20A.

    A case-insensitive heading match reads that as a schedule and swallows the act.
    """
    pages = [_page(["1. Short title.—This Act may be called the Test Act of 2020 and it "
                    "extends to the whole of India for all purposes whatsoever."]),
             _page(["the Schedule relating to any Category of projects or Infrastructure "
                    "Sub-Sectors may be amended by notification in the Official Gazette."]),
             _page(["20. Further provision.—Nothing in this Act shall affect any right "
                    "accrued before its commencement under any other law in force."])]
    assert ing._schedule_regions(pages) == [], "lowercase prose must not open a schedule"


def test_a_table_of_contents_entry_is_not_a_schedule():
    """"SCHEDULE" in the front matter is a contents line, not the schedule itself."""
    pages = [_page(["ARRANGEMENT OF SECTIONS", "SCHEDULE"])] + [_page(["filler"])] * 9
    assert ing._schedule_regions(pages) == []


def test_an_unenumerated_schedule_is_kept_whole():
    """Do not invent entry numbers. "Statement under section 58" is not entry 58."""
    pages = [_page(["1. Short title.—Something long enough to look like a real section "
                    "body for the purposes of this fixture."])] * 4 + [
        _page(["SCHEDULE I", "MAXIMUM FEES", "[See sub-section (1) of section 71.]",
               "Statement under section 58 ......... Three rupees.",
               "Statement under section 60 ......... One rupee.",
               "Intimation under section 61 ........ One rupee." + " padding" * 40])]
    out = ing._segment_schedules(pages)
    assert len(out) == 1 and out[0]["num"] == "Sch.I", out
    assert "Statement under section 58" in out[0]["text"]


def test_nested_numbering_does_not_create_duplicate_ids():
    """An inserted Order restarts at 1; that must not reopen entry 1."""
    filler = [_page(["1. Short title.—Long enough body text to be a plausible section for "
                     "this fixture and not be mistaken for a heading."])] * 4
    pages = filler + [_page([
        "THE SCHEDULE",
        "1. First entry.—Text of the first entry, long enough to count as substantive.",
        "2. Second entry.—Text of the second entry, also long enough to count properly.",
        "1. Nested rule.—This restarts numbering inside an inserted Order and must not "
        "open a new top-level entry at all.",
        "3. Third entry.—Text of the third entry, again long enough to be substantive."])]
    out = ing._segment_schedules(pages)
    nums = [s["num"] for s in out]
    assert len(nums) == len(set(nums)), f"duplicate ids: {nums}"
    # An unlabelled "THE SCHEDULE" gets a synthesised index, so entries are Sch.1.<n> —
    # the same shape the NDPS and Specific Relief schedules produce.
    assert nums == ["Sch.1.1", "Sch.1.2", "Sch.1.3"], nums
    assert "Nested rule" in out[1]["text"], "nested text should stay with its parent entry"


# ---------------------------------------------------------------------------------------
# The Mediation Act 2023 — four defects found when its schedules were brought in on
# 2026-08-08. Each is pinned by CONTENT, because each one passed a count.
# ---------------------------------------------------------------------------------------

def _mediation() -> dict[str, dict]:
    data = json.loads((FULLTEXT / "mediation_2023.fulltext.json").read_text(encoding="utf-8"))
    return {str(s["num"]): s for s in data["acts"][0]["sections"]}


def test_mediation_first_schedule_is_present():
    """Schedule I lists the disputes NOT fit for mediation — the Act's own exclusion list.

    It was absent entirely. `_schedule_regions` only scanned the first 20 lines of each
    page, and the Mediation Act runs straight out of s.65 into "THE FIRST SCHEDULE" in the
    MIDDLE of a page, so the heading was never seen and the act was indexed from Schedule
    II onwards.
    """
    secs = _mediation()
    entries = {n: s for n, s in secs.items() if n.startswith("Sch.I.")}
    assert len(entries) >= 13, f"Schedule I has only {len(entries)} entries"
    joined = " ".join(s["text"].lower() for s in entries.values())
    for phrase in ("prosecution for criminal offences",
                   "land acquisition",
                   "notified by the Central Government".lower()):
        assert phrase in joined, f"Schedule I does not mention {phrase!r}"


def test_no_schedule_entry_duplicates_a_body_section():
    """Widening that scan then swept the body INTO the schedule.

    The heading sits mid-page, so taking the whole page put ss.55-65 inside Schedule I and
    re-emitted them as Sch.I.55 … Sch.I.58 — the act's own provisions, duplicated into the
    schedule namespace under numbers that are not theirs.
    """
    secs = _mediation()
    body = {n: s["text"] for n, s in secs.items() if not n.startswith("Sch")}
    for num, sec in secs.items():
        if not num.startswith("Sch."):
            continue
        for bnum, btext in body.items():
            assert sec["text"] != btext, f"{num} is a verbatim copy of body s.{bnum}"


def test_the_amendment_sections_are_the_act_s_own_not_the_schedule_s():
    """ss.61 and 62 held the ARBITRATION ACT's substituted sections.

    The Sixth Schedule substitutes new ss.61 and 62 into the Arbitration and Conciliation
    Act 1996. The body segmenter reached into that schedule and took them as the Mediation
    Act's own ss.61-62, displacing "Amendment of Act 26 of 1996" and "Amendment of Act 27
    of 2006". Both neighbours on either side were correct, so nothing in a count showed it.
    """
    secs = _mediation()
    for num, act_no in (("61", "26 of 1996"), ("62", "27 of 2006")):
        text = secs[num]["text"]
        assert "Amendment of" in text and act_no in text, (
            f"s.{num} is not the amendment section for Act {act_no}:\n{text[:200]}")
        assert "Reference of conciliation in enactments" not in text, (
            f"s.{num} still holds the Sixth Schedule's substituted text")
    # ...and the schedule keeps its own copy, in its own namespace.
    assert "Reference of conciliation in enactments" in secs["Sch.VI.61"]["text"]


def test_the_statement_of_objects_and_reasons_is_not_in_the_corpus():
    """A bill's explanatory note is not law, and must not be retrievable as a schedule.

    The last schedule region ran to end-of-document, so the Statement of Objects and
    Reasons — signed by the minister who moved the bill, describing what it "seeks to" do —
    was ingested as Sch.X.2 / Sch.X.3 / Sch.X.4. Sch.X.4 was "The Bill seeks to achieve the
    above objectives. KIREN RIJIJU."
    """
    secs = _mediation()
    for num, sec in secs.items():
        low = sec["text"].lower()
        assert "the bill seeks to achieve" not in low, f"{num} is bill paperwork, not law"
        assert "statement of objects and reasons" not in low, f"{num} is the SOR"
    # Schedule X must be the real Tenth Schedule instead.
    tenth = " ".join(s["text"] for n, s in secs.items() if n.startswith("Sch.X"))
    assert "Consumer Protection Act, 2019" in tenth, "the Tenth Schedule is missing"
