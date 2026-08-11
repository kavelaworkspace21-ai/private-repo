"""The CPC's First Schedule — Orders and Rules — must be in the corpus and addressable.

Most of the civil procedure an advocate cites daily lives in the First Schedule, not in the
Code's 158 sections: Order VII Rule 11 (rejection of plaint), Order XXXIX Rules 1-2
(temporary injunctions), the whole of Order XXI (execution). None of it was in the corpus
before 2026-08-08. `body_before_schedule` correctly cut the Schedule away from the section
body — rules renumber from 1 inside every Order, so left in they overwrite the Code's own
numbering — and then nothing picked the cut-away part back up.

The generic Sch.<label>.<entry> namespace could not hold it either: `_schedule_regions` saw
ONE region in the whole Code, mislabelled "II", and emitted 34,998 characters as a single
blob. Hence the two-level Ord.<roman>.R.<rule> namespace these tests pin.

These are content assertions, not counts. A count passes just as happily when Order XXXIX
Rule 1 holds the text of Order XXXVIII Rule 5.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

CPC = Path(__file__).resolve().parent.parent / "app/legal_corpus/fulltext/cpc_1908.fulltext.json"


@pytest.fixture(scope="module")
def rules() -> dict[str, dict]:
    data = json.loads(CPC.read_text(encoding="utf-8"))
    return {str(s["num"]): s for s in data["acts"][0]["sections"]
            if str(s["num"]).startswith("Ord.")}


@pytest.fixture(scope="module")
def body() -> dict[str, dict]:
    data = json.loads(CPC.read_text(encoding="utf-8"))
    return {str(s["num"]): s for s in data["acts"][0]["sections"]
            if not str(s["num"]).startswith("Ord.")}


# (rule id, a phrase that must appear in its text). Chosen so a mis-filed neighbour fails:
# every phrase is unique to the rule it belongs to.
LANDMARKS = [
    ("Ord.VII.R.11",    "plaint shall be rejected"),
    ("Ord.VI.R.17",     "Amendment of pleadings"),
    ("Ord.VIII.R.1",    "Written statement"),
    ("Ord.IX.R.13",     "ex parte"),
    ("Ord.XXXIX.R.1",   "temporary injunction"),
    ("Ord.XXXIX.R.2",   "restrain repetition or continuance of breach"),
    ("Ord.XX.R.1",      "Judgment when pronounced"),
    ("Ord.XXI.R.1",     "Modes of paying money under decree"),
    ("Ord.XXII.R.3",    "death of one of several plaintiffs"),
    ("Ord.XLI.R.1",     "Form of appeal"),
    ("Ord.X.R.3",       "Substance of examination to be written"),
]


@pytest.mark.parametrize("num,phrase", LANDMARKS)
def test_landmark_rules_are_present_and_hold_their_own_text(rules, num, phrase):
    assert num in rules, f"{num} is not in the corpus"
    text = rules[num]["text"]
    assert phrase.lower() in text.lower(), (
        f"{num} does not contain {phrase!r} — it holds someone else's text:\n{text[:300]}"
    )


def test_every_order_of_the_first_schedule_is_present(rules):
    """Orders I-LI, plus the six inserted by later amendment acts."""
    got = {n.split(".")[1] for n in rules}
    base = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
            "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII", "XXIV",
            "XXV", "XXVI", "XXVII", "XXVIII", "XXIX", "XXX", "XXXI", "XXXII", "XXXIII",
            "XXXIV", "XXXV", "XXXVI", "XXXVII", "XXXVIII", "XXXIX", "XL", "XLI", "XLII",
            "XLIII", "XLIV", "XLV", "XLVI", "XLVII", "XLVIII", "XLIX", "L", "LI"]
    missing = [o for o in base if o not in got]
    assert not missing, f"Orders absent from the corpus: {missing}"
    inserted = ["XIII-A", "XV-A", "XVI-A", "XX-A", "XXVII-A", "XXXII-A"]
    assert not [o for o in inserted if o not in got], (
        f"inserted Orders absent: {[o for o in inserted if o not in got]}")


def test_the_commercial_division_order_xi_did_not_overwrite_the_original(rules):
    """TWO Orders XI are in force and they are different law.

    The Commercial Courts Act 2015 inserted an Order XI on disclosure and discovery for
    suits before a commercial division. It carries the same number as the original Order XI
    (Discovery and Inspection). Sharing one id would silently drop whichever was parsed
    first — the duplicate-id collision that cost twelve acts on 2026-07-12.
    """
    original = rules.get("Ord.XI.R.1")
    commercial = rules.get("Ord.XI-COM.R.1")
    assert original is not None, "the original Order XI Rule 1 is missing"
    assert commercial is not None, "the commercial-division Order XI Rule 1 is missing"
    assert original["text"] != commercial["text"], "both ids resolved to the same rule"
    assert "commercial" in commercial["text"].lower() or \
           "commercial" in (commercial.get("order_heading") or "").lower(), \
        "Ord.XI-COM is not the commercial-division Order"


# Rules the amendment acts OMITTED or REPEALED. Their absence is correct, and asserting it
# keeps a future "fix" from re-inserting repealed text as live law.
REPEALED = {
    "XXI": [60, 61, 62, 63, 70],   # omitted by the CPC (Amendment) Act 1976, s. 72
    "XLI": [7],                    # repealed
}


def test_rule_numbering_has_no_unexplained_holes(rules):
    """An Order whose rules skip a number lost one — unless an amendment act removed it."""
    by_order = defaultdict(set)
    for num in rules:
        _, order, _, rule = num.split(".", 3)
        by_order[order].add(int(re.match(r"\d+", rule).group()))

    problems = []
    for order, nums in by_order.items():
        holes = [n for n in range(1, max(nums) + 1)
                 if n not in nums and n not in REPEALED.get(order, [])]
        if holes:
            problems.append(f"Order {order} missing rules {holes}")
    assert not problems, (
        "rules absent from the corpus with no repeal on record: " + "; ".join(problems))


def test_the_repealed_rules_really_are_absent(rules):
    """Guards the exemption list above: if these ever parse, the list is hiding a real bug."""
    present = [f"Ord.{o}.R.{n}" for o, ns in REPEALED.items() for n in ns
               if f"Ord.{o}.R.{n}" in rules]
    assert not present, f"rules recorded as repealed are in the corpus: {present}"


def test_rules_never_collide_with_the_code_s_own_sections(rules, body):
    """The whole point of the namespace: a rule can never occupy a section number."""
    assert not (set(rules) & set(body))
    assert all(not str(n).startswith("Ord.") for n in body)
    # ...and the sections themselves are still intact.
    assert "res judicata" in body["11"]["text"].lower(), "s.11 is not the res judicata bar"
    assert len(body) >= 158, f"only {len(body)} sections; the Code has 158"


def test_appendix_forms_were_not_ingested_as_rules(rules):
    """Appendices A-I are model pleadings with blanks, not law.

    Their numbered paragraphs ("1. On the ……… day of ………, he lent the defendant ……
    rupees") parse as rules perfectly well, which is exactly the danger.
    """
    for num, sec in rules.items():
        assert "the above named plaintiff, states as follows" not in sec["text"], (
            f"{num} is a specimen plaint from an Appendix, not a rule")


def test_rules_carry_their_source_page(rules):
    """Provenance: an advocate turning to the cited page must find the rule there."""
    missing = [n for n, s in rules.items() if not s.get("page")]
    assert not missing, f"rules with no source page: {missing[:10]}"
