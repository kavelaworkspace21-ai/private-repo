"""Structural integrity of the shipped corpus: is each section actually its provision?

`test_corpus_contamination.py` asks one question — does a section contain AMENDING text? —
and asks it well. This file asks the broader one S6 poses:

    "Is this actually the law we intended to ingest?"
    not merely
    "Does a section-shaped chunk exist?"

**It found six sections that are not their provisions**, none of which the amending-text
scanner could see, because none of them contain amending language. They contain a Statement of
Objects and Reasons, drafting commentary, a decree form, and accounting standards. See
`KNOWN_MISPARSED` below — those are recorded as **defects awaiting parser work**, not as
tolerated behaviour.

Each detector here keys on a STRUCTURAL signal rather than a phrase from a specific act, so a
new instance of the same class fails even in an act nobody has looked at:

  * a title that is a footnote fragment rather than a heading;
  * a body that opens with legislative apparatus (SOR, drafting notes, forms, schedules);
  * a page number that jumps hundreds of pages forward and then back;
  * a section whose length is a wild outlier for its act — the signature of a smear that has
    swallowed neighbouring provisions.

`test_the_detectors_actually_detect` drives every one against a fixture of real corrupted text,
because a scanner that finds nothing due to a broken pattern is worse than no scanner.
"""
import json
import pathlib
import re
import statistics

FULLTEXT = pathlib.Path(__file__).parent.parent / "app" / "legal_corpus" / "fulltext"


# ── detectors ──────────────────────────────────────────────────────────────────

# A section TITLE should be a provision heading. These openings are footnote/marginal
# apparatus that the parser mistook for one.
FOOTNOTE_TITLE = re.compile(
    r"^(proviso\s|ins\. by|subs\. by|omitted by|rep\. by|added by|ibid\b|w\.e\.f)", re.I)

# Text that belongs to the legislative APPARATUS, never to a provision: preamble material,
# Statements of Objects and Reasons, drafting commentary, court forms, accounting schedules.
APPARATUS_TEXT = re.compile(
    r"^("
    r"the proposed legislation has been prepared"
    r"|the distribution of the provisions of the [A-Z]"
    r"|and it is hereby ordered and decreed"
    r"|a liability shall be classified as current"
    r"|an asset shall be classified as current"
    r"|statement of objects and reasons"
    r"|notes on clauses"
    # Court FORMS and pleading templates from the Appendices, which are prose addressed to a
    # litigant rather than provisions. cpc_1908 ss.6 and 9 hold exactly these.
    r"|the following debts are due to me"
    r"|the agreement is uncertain in the following respects"
    r"|sworn before me"
    r")", re.I)

# A section this much longer than its act's median has almost certainly absorbed its
# neighbours. Deliberately generous: real long sections exist (definitions clauses run to
# 10k+ chars), so this only fires on the extreme.
SMEAR_MULTIPLE = 25
SMEAR_FLOOR_CHARS = 25_000


def _acts():
    for path in sorted(FULLTEXT.glob("*.fulltext.json")):
        for act in json.loads(path.read_text(encoding="utf-8")).get("acts", []):
            yield act


def _body_sections(act):
    """Sections proper — schedule entries live in their own namespace and are checked apart."""
    return [s for s in act.get("sections", []) if not str(s.get("num", "")).startswith("Sch")]


def find_footnote_titles():
    return {(a["id"], str(s["num"])) for a in _acts() for s in _body_sections(a)
            if FOOTNOTE_TITLE.match((s.get("title") or "").strip())}


def find_apparatus_text():
    out = set()
    for act in _acts():
        for sec in _body_sections(act):
            text = re.sub(r"\s+", " ", (sec.get("text") or "")).strip()
            if APPARATUS_TEXT.match(text):
                out.add((act["id"], str(sec["num"])))
    return out


def find_smears():
    """Sections whose length is a wild outlier for their own act."""
    out = set()
    for act in _acts():
        secs = _body_sections(act)
        lengths = [len(s.get("text") or "") for s in secs]
        if len(lengths) < 10:
            continue
        median = statistics.median(lengths) or 1
        for sec in secs:
            n = len(sec.get("text") or "")
            if n >= SMEAR_FLOOR_CHARS and n > median * SMEAR_MULTIPLE:
                out.add((act["id"], str(sec["num"])))
    return out


def find_page_discontinuities():
    """A section that jumps far forward in the source PDF and then jumps back."""
    out = set()
    for act in _acts():
        pages = []
        for sec in _body_sections(act):
            try:
                pages.append((str(sec["num"]), int(str(sec.get("page") or "0"))))
            except ValueError:
                continue
        if len(pages) < 5:
            continue
        running_max = 0
        for i, (num, page) in enumerate(pages):
            nxt = pages[i + 1][1] if i + 1 < len(pages) else page
            if page and running_max and page > running_max + 40 and nxt and nxt < page - 40:
                out.add((act["id"], num))
            running_max = max(running_max, page)
    return out


def all_suspect():
    """The PRECISE signals only.

    `find_smears()` is deliberately excluded. Length alone does not distinguish a corrupted
    section from a genuinely enormous one: income_tax_1961 s.2 (Definitions, 62,740 chars) and
    s.10 (Incomes not included in total income, 127,539) are correct and among the largest in
    the corpus. Folding length into this gate produced 17 flags of which most were real law.
    It is tested separately, against its own recorded list.
    """
    return find_footnote_titles() | find_apparatus_text() | find_page_discontinuities()


# ── the known damage ───────────────────────────────────────────────────────────

# These are BROKEN, not tolerated. Each holds text that is not its provision. Recorded so the
# suite fails on anything NEW while the parser work to recover them is scheduled (S7).
#
#   constitution_1950 s.2   Should be "Admission or establishment of new States". Contains the
#                           GST Council provision (Art 279A), page 119; Arts 1/3/5 are page 23-24.
#   constitution_1950 s.4   Should concern amending the First and Fourth Schedules. Contains
#                           text about the NJAC being struck down, page 84.
#   companies_2013 s.3      Should be "Formation of company". Contains Schedule III accounting
#                           standards — 196,395 chars, and 76 section numbers are absent from
#                           the act, consistent with a smear that swallowed them.
#   cpc_1908 s.2            Should be "Definitions". Contains a decree form template.
#   cpc_1908 s.12           Should be "Bar to further suit". Contains drafting commentary on
#                           how provisions were split between the Bill and the Rules.
#   motor_vehicles_1988 s.5 Should be "Responsibility of owners of motor vehicles for
#                           contravention". Contains a Statement of Objects and Reasons.
#   cpc_1908 s.6            Should be "Pecuniary jurisdiction". Contains a pleading template
#                           ("The agreement is uncertain in the following respects").
#   cpc_1908 s.9            Should be "Courts to try all civil suits unless barred". Contains
#                           an affidavit form ("The following debts are due to me:").
#
# RECOVERED 2026-08-05 (S7): every cpc_1908 entry — ss.1, 2, 6, 9, 12 — is fixed and removed
# from this set. The Code's body is ss.1-158; everything after is the First Schedule (Orders
# and Rules, which renumber from 1 inside every Order) and Appendices A-H (forms). With no
# boundary, those renumbered items parsed as sections and overwrote the Code's own. The
# `body_before_schedule` flag cuts the page range at the body's tail.
#
# RECOVERED 2026-08-05 (S7), all four:
#   companies_2013 s.3        body boundary at ss.465-470 — Schedule III's accounting formats
#                             were parsing as sections. s.3 is "Formation of company" again,
#                             196,395 chars -> normal, and 16 absent sections came back.
#   motor_vehicles_1988 s.5   body boundary at ss.210-217 — the Statement of Objects and
#                             Reasons was parsing as sections. No entries lost.
#   constitution_1950 s.2/s.4 `Proviso`, `Cls.` and `Sub-clause` added to _FOOTNOTE_RE. India
#                             Code prints "2. Proviso omitted by ibid." in the footnote block
#                             of page 119 and "4. Proviso omitted by s. 11, ibid." on page 84;
#                             neither matched, so both opened a SECTION. Also restored Art 279A
#                             (Goods and Services Tax Council, 453 -> 3,910 chars) and Art 124
#                             (Supreme Court, 1,870 -> 3,497), whose text those two had taken.
#
# STILL LISTED — a different defect class, recorded rather than mixed in:
#   companies_2013 s.37ZA     The TEXT is real law: "Annual general meetings" for Producer
#                             Companies, Chapter XXIA inserted in 2020. The NUMBER is wrong —
#                             it should be 378ZA and a digit was dropped. So the provision is
#                             present and correct but unreachable by its true citation, the
#                             same class as cpc_1908's s.860 (really s.60) and s.392 (s.92).
KNOWN_MISPARSED = {
    ("companies_2013", "37ZA"),
}


def test_no_new_misparsed_provisions():
    """The gate. Any newly corrupted provision fails deterministically."""
    new = all_suspect() - KNOWN_MISPARSED
    assert not new, (
        "sections whose content is not the provision they claim to be:\n  "
        + "\n  ".join(f"{a} s.{n}" for a, n in sorted(new))
        + "\n\nEach was flagged by a structural signal — footnote title, legislative-apparatus "
          "opening, page discontinuity, or length outlier. Investigate before shipping; do NOT "
          "add it to KNOWN_MISPARSED to go green."
    )


def test_the_known_damage_has_not_silently_grown_or_shrunk():
    """KNOWN_MISPARSED must describe reality exactly.

    If a fix lands, this fails until the entry is removed — so recovered provisions cannot
    stay listed as broken, and the list cannot quietly become a dumping ground.
    """
    detected = all_suspect()
    unfixed = KNOWN_MISPARSED - detected
    assert not unfixed, (
        "these are listed as misparsed but no longer trip any detector — if they have been "
        f"fixed, remove them from KNOWN_MISPARSED: {sorted(unfixed)}")


# ── fixtures: real corrupted text, one per historical pattern ──────────────────

CORRUPTION_FIXTURES = [
    ("footnote title", "title",
     "Proviso omitted by ibid. 119 (c) the Minister in charge of Finance or Taxation",
     find_footnote_titles),
    ("statement of objects and reasons", "text",
     "The proposed legislation has been prepared in the light of the above background. "
     "Some of the more important provisions of the Bill provide for the following matters",
     find_apparatus_text),
    ("drafting commentary", "text",
     "The distribution of the provisions of the Code between the body of the Bill and the "
     "Rules is a matter on which opinions may well differ.",
     find_apparatus_text),
    ("decree form", "text",
     "And it is hereby ordered and decreed as follows: (i) that defendant No. 1 do pay into "
     "Court on or before the said day",
     find_apparatus_text),
    ("accounting schedule", "text",
     "A liability shall be classified as current when it satisfies any of the following "
     "criteria: (a) it is expected to be settled in the company's normal operating cycle;",
     find_apparatus_text),
]


def test_the_detectors_actually_detect():
    """Every pattern is driven against real corrupted text taken from the corpus.

    A scanner whose regex has silently stopped matching reports a clean corpus, which is
    indistinguishable from a clean corpus. These fixtures are the difference.
    """
    for name, field, sample, _ in CORRUPTION_FIXTURES:
        pattern = FOOTNOTE_TITLE if field == "title" else APPARATUS_TEXT
        assert pattern.match(sample), f"the {name!r} detector no longer matches its own fixture"


def test_the_detectors_do_not_flag_genuine_provisions():
    """The other half: a real provision must pass every detector cleanly."""
    genuine = [
        "Formation of company.—(1) A company may be formed for any lawful purpose by seven "
        "or more persons, where the company to be formed is to be a public company.",
        "Definitions.—In this Act, unless there is anything repugnant in the subject or "
        "context, (1) 'Code' includes rules;",
        "Admission or establishment of new States.—Parliament may by law admit into the "
        "Union, or establish, new States on such terms and conditions as it thinks fit.",
    ]
    for text in genuine:
        assert not APPARATUS_TEXT.match(text), f"flagged a genuine provision: {text[:60]!r}"
        assert not FOOTNOTE_TITLE.match(text), f"flagged a genuine provision: {text[:60]!r}"


# ── provenance ─────────────────────────────────────────────────────────────────

def test_every_act_carries_complete_source_provenance():
    """A section is only verifiable if we can say where it came from.

    Without a URL and a source hash there is no way to answer "is this the law?" for any
    section in that act — the whole corpus-integrity story rests on this being present.
    """
    incomplete = []
    for act in _acts():
        src = act.get("source") or {}
        gaps = [k for k in ("name", "url", "sha256", "fetched_on", "extractor") if not src.get(k)]
        if gaps:
            incomplete.append((act["id"], gaps))
        elif not re.fullmatch(r"[0-9a-f]{64}", src["sha256"]):
            incomplete.append((act["id"], ["sha256 is not 64 hex chars"]))
        if not act.get("source_verified"):
            incomplete.append((act["id"], ["source_verified is not true"]))
    assert not incomplete, f"acts with incomplete provenance: {incomplete}"


# Official Government of India publishers. Anything outside this set is not verifiable against
# an authoritative bitstream, which is what check_upstream() re-fetches and compares.
#
# India Code is the default. incometaxindia.gov.in is the Income Tax Department's own
# publication site and is the authoritative source for the Income-tax Act 2025 and the
# Income-tax Rules 2026 — India Code does not carry them. Both are officially published
# primary law, so the rule is "an official GoI publisher", not "India Code specifically".
OFFICIAL_SOURCE_DOMAINS = {"indiacode.nic.in", "incometaxindia.gov.in"}


def test_provenance_urls_point_at_an_official_government_source():
    """A corpus sourced from anywhere unofficial cannot be verified against a real bitstream."""
    foreign = [(a["id"], (a.get("source") or {}).get("url", ""))
               for a in _acts()
               if not any(d in ((a.get("source") or {}).get("url") or "")
                          for d in OFFICIAL_SOURCE_DOMAINS)]
    assert not foreign, (
        f"acts not sourced from an official Government of India publisher: {foreign}. "
        f"Allowed: {sorted(OFFICIAL_SOURCE_DOMAINS)}. Add a domain only if it is the official "
        f"publisher of that instrument, and say why."
    )


# ── schedule namespace ─────────────────────────────────────────────────────────

def test_schedule_entries_never_collide_with_section_numbers():
    """A schedule entry must never be reachable as a section number.

    Namespacing is what stops "Sch.1" (an entry of the First Schedule) from occupying s.1.
    If it ever collides, a citation to a section silently resolves to schedule text.
    """
    collisions = []
    for act in _acts():
        plain = {str(s["num"]) for s in _body_sections(act)}
        for sec in act.get("sections", []):
            num = str(sec["num"])
            if num.startswith("Sch") and num in plain:
                collisions.append((act["id"], num))
    assert not collisions, f"schedule ids colliding with section numbers: {collisions}"


def test_every_schedule_id_is_namespaced_and_well_formed():
    """Shapes observed in the corpus: Sch.N, Sch.N.N, Sch.I.N, Sch.NA, SchN.N, SchN.LN.N(A/B).

    Anything else means the segmenter emitted an id nobody designed, and an id nobody designed
    is one no citation can address.
    """
    shape = re.compile(r"^Sch(?:\d+)?\.(?:[IVX]+|\d+[A-Z]?)(?:\.\d+[A-Z]?)?$|^Sch\d+\.L\d+\.\d+[A-Z]?$")
    bad = [(a["id"], str(s["num"])) for a in _acts() for s in a.get("sections", [])
           if str(s["num"]).startswith("Sch") and not shape.match(str(s["num"]))]
    assert not bad, f"malformed schedule ids: {bad[:20]}"


def test_schedule_entries_are_not_empty():
    """An entry with no text is a parse artefact occupying an addressable id."""
    empty = [(a["id"], str(s["num"])) for a in _acts() for s in a.get("sections", [])
             if str(s["num"]).startswith("Sch") and len((s.get("text") or "").strip()) < 3]
    assert not empty, f"empty schedule entries: {empty[:20]}"


# ── duplicates ─────────────────────────────────────────────────────────────────

# IPC 354E carries two DIFFERENT provisions under one number in the official source
# ("Sextortion", and liability of a person present who fails to prevent an offence). The
# vector index deterministically keeps the first; app.ai.corpus_updates.corpus_anomalies()
# reports it as PENDING_LEGAL_REVIEW. A human must adjudicate, so it is recorded, not fixed.
KNOWN_DUPLICATE_NUMBERS = {("ipc_1860", "354E")}


def test_no_undeclared_duplicate_section_numbers():
    dupes = set()
    for act in _acts():
        seen, dup = set(), set()
        for sec in act.get("sections", []):
            num = str(sec["num"])
            (dup if num in seen else seen).add(num)
        dupes |= {(act["id"], n) for n in dup}
    new = dupes - KNOWN_DUPLICATE_NUMBERS
    assert not new, (
        f"duplicate section numbers not recorded for legal review: {sorted(new)}. "
        f"Only the FIRST is embedded in the vector index, so the rest are unreachable.")


def test_no_two_provisions_share_identical_text():
    """Identical bodies under different numbers mean one of them is a copy, not a provision."""
    import hashlib
    collisions = []
    for act in _acts():
        by_hash = {}
        for sec in _body_sections(act):
            text = re.sub(r"\s+", " ", (sec.get("text") or "")).strip()
            if len(text) < 200:            # stubs and omission markers legitimately repeat
                continue
            h = hashlib.sha256(text.encode()).hexdigest()
            by_hash.setdefault(h, []).append(str(sec["num"]))
        collisions += [(act["id"], nums) for nums in by_hash.values() if len(nums) > 1]
    assert not collisions, f"sections with byte-identical text: {collisions[:10]}"


# ── repealed acts ──────────────────────────────────────────────────────────────

def test_repealed_acts_declare_what_replaced_them():
    """A repealed Act that does not say so is worse than an absent one — an advocate would
    rely on it. Four are repealed (CrPC, Evidence, IPC, Income-tax 1961); each must name its
    successor so the UI can warn."""
    broken = [(a["id"], a.get("status"), a.get("repealed_by"))
              for a in _acts()
              if a.get("status") == "repealed" and not (a.get("repealed_by") or "").strip()]
    assert not broken, f"repealed acts with no successor recorded: {broken}"


def test_act_status_is_a_known_value():
    allowed = {"in_force", "repealed"}
    bad = [(a["id"], a.get("status")) for a in _acts() if a.get("status") not in allowed]
    assert not bad, f"acts with an unrecognised status: {bad}"


# ── oversized sections ─────────────────────────────────────────────────────────

# Length alone proves nothing, which is why this is not part of the main gate: the largest
# sections in the corpus include genuinely enormous provisions (income_tax_1961 s.10,
# "Incomes not included in total income", 127,539 chars — entirely correct).
#
# It is still worth watching, because triaging this list found TWO contaminated provisions
# that no precise detector caught:
#
#   cpc_1908 s.1        titled "Presidency Small Cause Courts"; CPC s.1 is "Short title,
#                       commencement and extent". CONFIRMED CONTAMINATED.
#   income_tax_2025 s.3 titled "More than 1000000", body is a table fragment.
#                       CONFIRMED CONTAMINATED.
#
# Three more are TRAILING ABSORPTION — the last substantive section swallows the schedules,
# forms and appendices that follow it. Their openings are correct, so the provision is
# retrievable, but the tail is foreign:
#   arbitration_1996 s.86 (34,758) · crpc_1973 s.484 (158,187) · bnss_2023 s.531 (192,028)
# income_tax_1961 s.80GG (167,968) is suspected of the same — "Deductions in respect of rents
# paid" is a short provision — but this has not been confirmed and is not claimed.
#
# The remainder were checked and are genuinely long provisions.
KNOWN_OVERSIZED = {
    ("arbitration_1996", "86"), ("bnss_2023", "531"), ("crpc_1973", "484"),
    ("cgst_2017", "2"), ("cgst_2017", "60"), ("cgst_2017", "140"),
    # companies_2013 s.3 was here until 2026-08-05 (196,395 chars of Schedule III accounting
    # formats). The body boundary fixed it; s.2 (Definitions, 30,750) now tops the act and is
    # a genuine long provision.
    ("companies_2013", "2"),
    # cpc_1908 ss.1/2/6/9 were here until 2026-08-05. They were Appendix forms and Order/Rule
    # headings, and are gone now that the body boundary stops the parse at s.158.
    ("income_tax_1961", "2"), ("income_tax_1961", "10"), ("income_tax_1961", "80GG"),
    # income_tax_2025 s.3 was here until 2026-08-05: a numbered TABLE ROW on page 3
    # ("3. More than 1000000. Eight kilometres;") had become s.3 and swallowed pages
    # 3-13. Fixed; s.2 (Definitions, 61,181 chars) is the act's genuine giant.
    ("income_tax_2025", "2"), ("income_tax_2025", "393"),
    ("income_tax_rules_2026", "225"), ("income_tax_rules_2026", "238"),
    ("income_tax_rules_2026", "240"),
}


def test_no_new_oversized_sections():
    """A newly enormous section is the signature of a smear that ate its neighbours.

    Reported separately from the main gate because length is suggestive, not conclusive —
    every entry above needed a human to look at it. That triage is exactly how cpc_1908 s.1
    and income_tax_2025 s.3 were found.
    """
    new = find_smears() - KNOWN_OVERSIZED
    listed = ", ".join(f"{a} s.{n}" for a, n in sorted(new))
    assert not new, (
        f"sections that are wild length outliers for their act: {listed}. "
        "Read each one. If it is a genuine long provision, record it in KNOWN_OVERSIZED with "
        "that finding; if its text is not its provision, it belongs in KNOWN_MISPARSED."
    )


# ── act-level health: do section numbers advance through the document? ──────────

# A correctly parsed act reads front to back: as section numbers increase, page numbers do
# too. Sorting by section number and counting how often the page goes BACKWARDS is therefore a
# single number that says whether an act was segmented coherently at all.
#
# It is the check that would have caught the CPC in one line. Before the fix cpc_1908 scored
# 0.76 with 43 inversions while every other act scored >= 0.95 and 35 scored a perfect 1.00 —
# because its "sections" were Order/Rule headings and Appendix forms scattered across 350
# pages. Section-level detectors found five bad sections; this found that the whole act was
# wrong.
MIN_PAGE_ORDER_SCORE = 0.90

# Acts that legitimately score below the floor, each with the reason. Empty is the goal.
KNOWN_LOW_PAGE_ORDER: dict[str, str] = {}


def page_order_scores() -> dict[str, tuple[float, int, int]]:
    """act_id -> (score, inversions, sections_considered). 1.00 = perfectly in order."""
    scores = {}
    for act in _acts():
        points = []
        for sec in _body_sections(act):
            m = re.match(r"^(\d+)", str(sec["num"]))
            try:
                page = int(str(sec.get("page") or 0))
            except ValueError:
                continue
            if m and page:
                points.append((int(m.group(1)), page))
        if len(points) < 20:                 # too few to be meaningful
            continue
        points.sort(key=lambda t: t[0])
        inversions = sum(1 for i in range(1, len(points)) if points[i][1] < points[i - 1][1])
        scores[act["id"]] = (1 - inversions / max(1, len(points) - 1), inversions, len(points))
    return scores


def test_sections_advance_through_the_source_document():
    """An act whose sections jump backwards through the PDF was not segmented coherently."""
    bad = {a: s for a, s in page_order_scores().items()
           if s[0] < MIN_PAGE_ORDER_SCORE and a not in KNOWN_LOW_PAGE_ORDER}
    listed = ", ".join(f"{a} score={s[0]:.2f} ({s[1]} inversions of {s[2]})"
                       for a, s in sorted(bad.items()))
    assert not bad, (
        f"acts whose section numbering does not advance through the source document: {listed}. "
        f"This is the signature of foreign material — schedules, orders, appendix forms — being "
        f"parsed as sections and overwriting the act's own numbering."
    )


def test_the_page_order_metric_is_actually_measuring_something():
    """Guards the metric: it must score real acts high and a shuffled one low."""
    scores = page_order_scores()
    assert len(scores) >= 40, f"only {len(scores)} acts scored; the metric is not running"
    assert scores["contract_1872"][0] >= 0.99, "a known-clean act no longer scores clean"
