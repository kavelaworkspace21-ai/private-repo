"""C-01b — the TOC-skip segmentation chooser (corpus poisoning guard).

A statute PDF whose front matter is a long ARRANGEMENT OF SECTIONS must be parsed from
the BODY (substantial text per section), never from the table of contents (one-line
marginal notes). This was caught live: IPC s.302 parsed as 22 chars of heading."""
from app.ai.ingest_statutes import (
    _segment_sections, _seg_score, _last_article_page,
    _segment_seventh_schedule, _segment_tenth_schedule,
)


def _page(lines):
    return "\n".join(lines)


BODY = {
    1: "1. Short title and extent.—This Act may be called the Test Act and it extends "
       "to the whole of India except as otherwise provided, and shall come into force "
       "on such date as the Government may by notification appoint for the purpose.",
    2: "2. Definitions.—In this Act, unless the context otherwise requires, the term "
       "'court' means a civil court of competent jurisdiction and includes any officer "
       "empowered to exercise the powers of such a court under any law in force.",
    3: "3. Punishment for contravention.—Whoever contravenes any provision of this Act "
       "shall be punishable with imprisonment for a term which may extend to seven "
       "years and shall also be liable to fine as the court may in its discretion fix.",
    4: "4. Cognizance of offences.—No court shall take cognizance of any offence under "
       "this Act except upon a complaint in writing made by an officer authorised in "
       "this behalf by the Government by general or special order published officially.",
    5: "5. Power to make rules.—The Government may, by notification in the Official "
       "Gazette, make rules for carrying out the purposes of this Act including rules "
       "as to the manner of inquiry and the fees payable in respect of applications.",
    6: "6. Repeal and savings.—The enactments specified in the Schedule are hereby "
       "repealed to the extent mentioned therein, provided that anything done under "
       "the repealed enactments shall be deemed to have been done under this Act.",
    7: "7. Delegation.—The Government may delegate any power conferred on it by this "
       "Act to any officer subordinate to it subject to such conditions as it thinks "
       "fit and every such delegation shall be published in the Official Gazette.",
    8: "8. Protection of action taken in good faith.—No suit or prosecution shall lie "
       "against any person for anything which is in good faith done or intended to be "
       "done under this Act or the rules made thereunder by any authority whatsoever.",
}
TOC = [f"{n}. {BODY[n].split('.—')[0].split('. ', 1)[1]}." for n in BODY]


def test_toc_locked_pdf_parses_the_body_not_the_contents():
    pages = [
        _page(["THE TEST ACT, 2020", "ARRANGEMENT OF SECTIONS", "SECTIONS"] + TOC),
        _page([BODY[1], BODY[2], BODY[3], BODY[4]]),
        _page([BODY[5], BODY[6], BODY[7], BODY[8]]),
    ]
    secs = {s["num"]: s for s in _segment_sections(pages)}
    assert len(secs) == 8
    # s.3 must be the PROVISION (with the punishment words), not the one-line TOC entry
    assert "seven" in secs["3"]["text"] and len(secs["3"]["text"]) > 150
    lens = sorted(len(s["text"]) for s in secs.values())
    assert lens[len(lens) // 2] > 150                     # median = body-sized


def test_clean_pdf_without_toc_still_parses_fully():
    pages = [_page([BODY[1], BODY[2], BODY[3], BODY[4]]),
             _page([BODY[5], BODY[6], BODY[7], BODY[8]])]
    secs = {s["num"]: s for s in _segment_sections(pages)}
    assert len(secs) == 8 and "seven" in secs["3"]["text"]


def test_score_prefers_substance_over_count():
    toc_parse = [{"num": str(i), "text": "Heading only."} for i in range(1, 60)]
    body_parse = [{"num": str(i), "text": "x" * 400} for i in range(1, 12)]
    assert _seg_score(body_parse) > _seg_score(toc_parse)


def test_amendment_bracket_prefix_is_recognised():
    """India Code substitution marker "N[" before a section number (e.g. "2[304B. …")
    must not hide the section. Without this, every substituted/inserted provision
    (304B, 375, 498A body …) was invisible to the parser — a corpus-integrity hole."""
    pages = [_page([
        '2[304B. Dowry death.—(1) Where the death of a woman is caused by any burns '
        'or bodily injury within seven years of her marriage, such death shall be '
        'called dowry death and the husband shall be deemed to have caused it.]',
        '375. Rape.—A man is said to commit rape if he penetrates against consent, '
        'and shall be punished as provided in section 376 of this Code accordingly.',
    ])]
    secs = {s["num"]: s for s in _segment_sections(pages)}
    assert "304B" in secs and "375" in secs
    assert "Dowry death" in secs["304B"]["text"]


def test_editorial_footnotes_are_dropped():
    """Amendment footnotes ("1. Subs. by Act 36 of 1957 …") match the section-start
    pattern but are never statute bodies; they must be filtered before segmentation."""
    from app.ai.ingest_statutes import _drop_footnotes
    lines = [
        ("34. Acts done by several persons in furtherance of common intention.—When a "
         "criminal act is done by several persons each is liable as if done by him alone.", 5),
        ("1. Subs. by Act 36 of 1957, s. 3 and Schedule II, for certain words.", 5),
        ("2. The words British India have successively been amended by the A.O. 1948.", 5),
    ]
    kept = _drop_footnotes(lines)
    assert len(kept) == 1 and kept[0][0].startswith("34.")


def test_wrapped_heading_is_recovered_when_opted_in():
    """The Constitution prints long marginal headings that spill onto a second line before
    the '.—' body separator. Plain _seg_dash only opens a section when the em-dash is on the
    number's line, so at Constitution scale (where the dash strategy wins the fitness score)
    it merged 45 such articles (incl. Art. 72 pardons) into the PREVIOUS article — a citation
    bug (a query for Art. 71 returned Art. 72's text). `wrapped=True` adds the wrapped-heading
    strategy so the em-dash arriving on a continuation line still opens the section."""
    pages = [_page([
        "71. Matters relating to the election of a President or Vice-President.—All doubts "
        "and disputes arising out of or in connection with the election of a President or "
        "Vice-President shall be inquired into and decided by the Supreme Court accordingly.",
        # Art. 72's heading WRAPS: no em-dash on the number line; it arrives on the next line.
        "72. Power of President to grant pardons, etc., and to suspend, remit or",
        "commute sentences in certain cases.—(1) The President shall have the power to "
        "grant pardons, reprieves, respites or remissions of punishment in all cases.",
    ])]
    wrapped = {s["num"]: s for s in _segment_sections(pages, wrapped=True)}
    # 72 is its own article, its wrapped heading is joined, and 71 is not contaminated
    assert "72" in wrapped and "pardon" in wrapped["72"]["text"].lower()
    assert "pardon" not in wrapped["71"]["text"].lower()
    assert wrapped["72"]["title"].startswith("Power of President to grant pardons")


def test_wrapped_opt_in_does_not_disturb_ordinary_dash_parsing():
    """wrapped=True is opt-in precisely because it must not change ordinary Acts whose
    headings already sit on one line — the default candidate pool stays authoritative there.
    The clean single-line BODY fixture must parse identically with and without wrapped."""
    pages = [_page([BODY[1], BODY[2], BODY[3], BODY[4], BODY[5], BODY[6], BODY[7], BODY[8]])]
    plain = {n: s["text"] for n, s in ((x["num"], x) for x in _segment_sections(pages))}
    wrap = {n: s["text"] for n, s in ((x["num"], x) for x in _segment_sections(pages, wrapped=True))}
    assert plain == wrap


def test_pre_schedule_boundary_stops_schedule_paras_shadowing_articles():
    """The Constitution's Schedules renumber from 1, so a Schedule paragraph collides with a
    low-numbered article (Sixth Schedule para 21 'Amendment of the Schedule' vs Article 21
    'Protection of life'). _last_article_page finds the article/Schedule boundary by the tail
    articles (392-399), so segmenting only the pre-Schedule pages keeps the article namespace
    clean."""
    pages = [
        _page(["21. Protection of life and personal liberty.—No person shall be deprived "
               "of his life or personal liberty except according to procedure by law."]),
        _page(["392. Power of the President to remove difficulties.—The President may by "
               "order make such provision as appears necessary for removing any difficulty.",
               "395. Repeals.—The Indian Independence Act, 1947, is hereby repealed."]),
        # A Schedule page: numbering RESETS; para 21 would otherwise overwrite Article 21.
        _page(["THE SIXTH SCHEDULE",
               "21. Amendment of the Schedule.—Parliament may from time to time by law "
               "amend by way of addition, variation or repeal any of the provisions herein."]),
    ]
    end = _last_article_page(pages, 392, 399)
    assert end == 1                                   # page index 1 holds Art. 392/395
    secs = {s["num"]: s for s in _segment_sections(pages[: end + 1], wrapped=True)}
    assert "life" in secs["21"]["text"].lower()       # real Article 21, not the Schedule para
    assert "Amendment of the Schedule" not in secs["21"]["text"]


def test_seventh_schedule_splits_lists_into_namespaced_entries():
    """The Constitution's SEVENTH SCHEDULE (Article 246) holds the Union/State/Concurrent Lists,
    each renumbering entries from 1. They must be parsed into a separate 'Sch7.L{1,2,3}.<entry>'
    namespace so an entry (e.g. State List Entry 46 'Taxes on agricultural income') never
    collides with an article, and each List's entry number is preserved."""
    pages = [
        _page(["SEVENTH SCHEDULE", "(Article 246)", "List I—Union List",
               "1. Defence of India and every part thereof.",
               "6. Atomic energy and mineral resources necessary for its production.",
               "List II—State List",
               "6. Public health and sanitation; hospitals and dispensaries.",
               "46. Taxes on agricultural income.",
               "List III—Concurrent List",
               "1. Criminal law, including all matters in the Indian Penal Code.",
               "5. Marriage and divorce; infants and minors; adoption."]),
        _page(["EIGHTH SCHEDULE", "Languages."]),
    ]
    secs = {s["num"]: s for s in _segment_seventh_schedule(pages)}
    # entries live in per-List namespaces; identical entry numbers across Lists don't collide
    assert "Sch7.L1.1" in secs and "Sch7.L2.6" in secs and "Sch7.L3.1" in secs
    assert "agricultural income" in secs["Sch7.L2.46"]["text"].lower()
    assert secs["Sch7.L2.46"]["title"].startswith("Seventh Schedule, State List, Entry 46")
    assert "criminal law" in secs["Sch7.L3.1"]["text"].lower()
    # the Union-List Entry 1 and Concurrent-List Entry 1 are DISTINCT rows
    assert "defence" in secs["Sch7.L1.1"]["text"].lower()
    assert secs["Sch7.L1.1"]["text"] != secs["Sch7.L3.1"]["text"]


def test_seventh_schedule_absent_returns_empty_not_error():
    """A PDF without a Seventh Schedule (any ordinary Act) must yield [] , never raise."""
    assert _segment_seventh_schedule([_page(["1. Short title.—This Act may be called ..."])]) == []


def test_tenth_schedule_recovers_starred_paragraph_seven():
    """The Tenth Schedule (anti-defection) paragraphs go into 'Sch10.<para>'. Paragraph 7
    (Bar of jurisdiction of courts) is printed with a leading '*' footnote marker in the source
    ('*7. Bar of jurisdiction…') which hides it from the numbered-start pattern — it must be
    stripped and recovered, and the content heading (not the TOC entry) must be used."""
    pages = [
        _page(["TENTH SCHEDULE—Provisions as to disqualification on ground of defection."]),  # TOC
        _page(["1[TENTH SCHEDULE", "Provisions as to disqualification on ground of defection",
               "1. Interpretation.—In this Schedule, unless the context otherwise requires, "
               "'House' means either House of Parliament or the Legislature of a State.",
               "2. Disqualification on ground of defection.—(1) A member shall be disqualified "
               "if he has voluntarily given up his membership of his political party.",
               "*7. Bar of jurisdiction of courts.—Notwithstanding anything in this Constitution, "
               "no court shall have any jurisdiction in respect of any matter under this Schedule.",
               "8. Rules.—The Chairman or the Speaker may make rules for giving effect to this "
               "Schedule and every such rule shall be laid before the House."]),
        _page(["ELEVENTH SCHEDULE", "1. Agriculture, including agricultural extension."]),
    ]
    secs = {s["num"]: s for s in _segment_tenth_schedule(pages)}
    assert "Sch10.7" in secs and "jurisdiction" in secs["Sch10.7"]["text"].lower()
    assert secs["Sch10.7"]["title"].startswith("Tenth Schedule, Paragraph 7 — Bar of jurisdiction")
    assert "Sch10.2" in secs and "defection" in secs["Sch10.2"]["text"].lower()
    # bounded by ELEVENTH SCHEDULE — the 11th-Schedule 'Agriculture' entry must NOT be pulled in
    assert not any("agriculture" in s["text"].lower() for s in secs.values())


def test_chain_rules_rejects_everything_that_breaks_the_ascending_sequence():
    """Rules-gazette segmentation (Income-tax Rules, 2026): a numbered start is accepted ONLY
    if it continues the ascending chain. Table rows, a quoted Act section ("379.—"), and
    annexure restarts all violate the chain and must be rejected structurally — the first
    pass without this let a trailing annexure item clobber rule 1."""
    from app.ai.ingest_statutes import _segment_chain_rules
    pages = [_page([
        "1. Short title and commencement.—(1) These rules may be called the Test Rules, 2026.",
        "2. Definitions.—In these rules, 'Act' means the Test Act, 2025.",
        "3. Third rule.—Substance of the third rule.",
        "4. Fourth rule.—Substance of the fourth rule.",
        "5. Fifth rule.—Substance of the fifth rule, with a table below:",
        "TABLE",
        "2. Deposit with — Cash deposits exceeding fifty lakh rupees.",   # table row BELOW chain → rejected
        "379. — (1) The Dispute Resolution Committee shall receive applications.",  # Act quote: jump >30 → rejected
    ]), _page([
        "6. Sixth rule.—Text of the sixth rule follows here.",
        "1. Annexure item.—This trailing annexure restart must NOT clobber rule 1.",
    ])]
    secs = {s["num"]: s for s in _segment_chain_rules(pages)}
    # rule 1 is the REAL rule 1 (annexure restart rejected)
    assert "Short title" in secs["1"]["text"]
    assert "Annexure" not in secs["1"]["text"][:40]
    # the quoted '379.' never became a rule; the low table row never clobbered rule 2
    assert "379" not in secs
    assert "Definitions" in secs["2"]["text"] and "Deposit" not in secs["2"]["text"][:30]
    # chain continues across the junk: rule 6 exists with its own text
    assert "6" in secs and "Sixth rule" in secs["6"]["text"]


def test_shipped_corpus_carries_recovered_stubs_and_clean_neighbours():
    """Data pin for the 2026-07-20 completeness slice: the shipped fulltext files must keep
    the recovered repeal stubs, the full Limitation Schedule, and the DE-CONTAMINATED IPC
    ss.57/60 (their old texts ended with the orphaned tails of the dropped s.58/s.61 stubs)."""
    import json
    from pathlib import Path
    ft = Path(__file__).resolve().parent.parent / "app" / "legal_corpus" / "fulltext"

    def load(aid):
        d = json.loads((ft / f"{aid}.fulltext.json").read_text(encoding="utf-8"))
        return {s["num"]: s for s in d["acts"][0]["sections"]}

    lim = load("limitation_1963")
    assert len(lim) == 169, "Limitation = 32 body + 137 Schedule articles"
    for n in ("28", "32", "Sch.136", "Sch.137"):
        assert n in lim
    assert "right to apply accrues" in lim["Sch.137"]["text"].lower()

    ipc = load("ipc_1860")
    for n in ("15", "58", "59", "61"):
        assert n in ipc and "rep. by" in ipc[n]["text"].lower()
    assert "Criminal Procedure (Amendment)" not in ipc["57"]["text"], "s.58 stub tail must be gone"
    assert "(16 of 1921)" not in ipc["60"]["text"], "s.61 stub tail must be gone"

    ev = load("evidence_1872")
    assert "2" in ev and "rep. by" in ev["2"]["text"].lower()


def test_footnote_filter_keeps_bracketed_repeal_stubs():
    """Regression (2026-07-20): India Code prints a REPEALED section's surviving stub as
    "28. [Amendment of certain Acts.]—Rep. by …" — a real section entry. The citation-marker
    footnote filter (_FOOTNOTE_RE2) was eating these (Limitation ss.28/32, IPC ss.15/58/59/61,
    Evidence s.2 all vanished; the orphaned stub tails corrupted IPC ss.57/60). A bracketed
    heading right after the number marks a section, never a footnote."""
    from app.ai.ingest_statutes import _drop_footnotes
    lines = [
        ("28. [Amendment of certain Acts.]—Rep. by Repealing and Amending Act, 1974", 1),
        ("32. [Repeal.]—Rep. by Repealing and Amending Act, 1974 (56 of 1974), s. 2", 1),
        ("15. [Definition of “British India”.] Rep. by the A. O. 1937.", 1),
        ("1. Subs. by Act 52 of 1964, s. 3 and the Second Schedule, for the words", 1),  # real footnote
        ("2. Ins. by Act 26 of 1955, s. 117 and the Sch. (w.e.f. 1-1-1956).", 1),        # real footnote
    ]
    kept = [ln for ln, _ in _drop_footnotes(lines)]
    assert any(ln.startswith("28.") for ln in kept), "bracketed repeal stub s.28 must survive"
    assert any(ln.startswith("32.") for ln in kept), "bracketed repeal stub s.32 must survive"
    assert any(ln.startswith("15.") for ln in kept), "bracketed repeal stub s.15 must survive"
    assert not any("Subs. by Act 52" in ln for ln in kept), "real Subs. footnote must still drop"
    assert not any("Ins. by Act 26" in ln for ln in kept), "real Ins. footnote must still drop"


def test_chain_loose_starts_recovers_glued_and_spaced_sections():
    """ITA-2025 print pathologies (`chain_loose_starts`, opt-in): some section starts are
    glued to the number ("476.22[(1)…", "480.If…") or space the number off the period
    ("95 . The provision…"). The loose pattern recovers them, but ONLY under the chain
    constraint — a glued duplicate of the current section and a decimal ("100.5 per cent")
    must still be rejected. Off by default: without the flag the strict parse is unchanged."""
    import app.ai.ingest_statutes as ing
    from app.ai.ingest_statutes import _segment_chain_rules
    pages = [_page([
        "1. Short title.—This Act may be called the Test Act, 2025.",
        "2. Definitions.—In this Act, 'tax year' means the twelve months.",
        "3 . (1) Irrespective of anything in section 2, these amounts shall not be deducted.",  # spaced-off period
        "4.22[(1) If a person fails to pay the tax deducted at source by him.",                 # glued amend-bracket
        "4.Without prejudice to this Act, a person shall be liable.",   # glued DUPLICATE of current section → rejected
        "5.If a person wilfully attempts to evade any tax, he shall be punishable.",           # glued capital start
        "The rate shall be 100.5 per cent of the amount in default.",   # decimal — must never open a section
        "6. Sixth section.—Normal strict start still works.",
    ])]
    old = ing._CHAIN_LOOSE
    try:
        ing._CHAIN_LOOSE = True
        secs = {s["num"]: s for s in _segment_chain_rules(pages)}
        assert set(secs) == {"1", "2", "3", "4", "5", "6"}
        assert "Irrespective" in secs["3"]["text"]
        assert "22[(1) If a person fails" in secs["4"]["text"]
        # glued duplicate stayed inside s.4 (chain: equal number, no suffix → rejected)
        assert "Without prejudice" in secs["4"]["text"]
        assert "wilfully attempts" in secs["5"]["text"]
        # the decimal line stayed body text inside s.5
        assert "100.5 per cent" in secs["5"]["text"]
        ing._CHAIN_LOOSE = False
        strict = {s["num"] for s in _segment_chain_rules(pages)}
        assert strict == {"1", "2", "6"}   # flag off → old behaviour, recoveries invisible
    finally:
        ing._CHAIN_LOOSE = old


def test_reseed_raises_when_the_old_corpus_cannot_be_deleted(monkeypatch, tmp_path):
    """Regression (2026-07-20): sqlite "disk full" made delete_collection fail; the old
    except-pass swallowed it and reseed() returned the STALE 8,072-chunk corpus as if
    freshly seeded. If the old collection survives the delete, reseed must raise.

    Updated 2026-07-29 for build-then-swap: the delete now happens AFTER a successful
    build, so the stub has to get through the build phase to reach the case under test.
    The property being pinned is unchanged.
    """
    import pytest as _pytest

    import app.ai.vector_store as vs

    class StubCol:
        def __init__(self, name, n):
            self.name, self._n = name, n
        def count(self):
            return self._n
        def modify(self, name=None, **kw):
            self.name = name

    class StubClient:
        def __init__(self):
            self.built = {}
        def list_collections(self):
            return []
        def create_collection(self, name, **kw):
            self.built[name] = StubCol(name, 0)
            return self.built[name]
        def get_collection(self, name):
            if name in self.built:
                return self.built[name]
            return StubCol(name, 8072)          # the live collection survives the delete
        def delete_collection(self, name):
            if name == vs.BUILD_COLLECTION_NAME:
                raise ValueError("no such collection")   # nothing to scrap; harmless
            raise RuntimeError("database or disk is full")

    monkeypatch.setattr(vs, "RESEED_LOCK_PATH", tmp_path / ".reseed.lock")
    monkeypatch.setattr(vs, "_store_size_bytes", lambda: 0)
    monkeypatch.setattr(vs, "disk_free_bytes", lambda *a, **k: 50 * 1024 ** 3)
    monkeypatch.setattr(vs, "_embedding_fn", lambda: None)
    # A build that is complete, so the shrink guard passes and we reach the delete.
    monkeypatch.setattr(vs, "_seed_collection",
                        lambda col, **kw: setattr(col, "_n", 8072))

    old_client, old_col = vs._client, vs._collection
    try:
        vs._client, vs._collection = StubClient(), None
        with _pytest.raises(RuntimeError, match="reseed aborted"):
            vs.reseed()
    finally:
        vs._client, vs._collection = old_client, old_col


def test_seeder_dedups_ids_so_one_bad_section_cant_wipe_the_corpus():
    """Regression (2026-07-12): a duplicate section id made ChromaDB reject the whole
    batch, aborting the seed and silently dropping every act after the offender (12 acts,
    incl. the NI Act, vanished). The seeder must de-dup ids (first-wins) before upsert."""
    import app.ai.vector_store as vs

    captured = {}
    class FakeCol:
        def upsert(self, documents, metadatas, ids):
            # ChromaDB raises on a duplicate id within a batch — emulate that contract.
            if len(set(ids)) != len(ids):
                raise ValueError("Expected IDs to be unique")
            captured.setdefault("ids", []).extend(ids)

    # two acts, the first with a duplicate section id; without de-dup the 2nd act is lost
    import json, tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "a_1900.fulltext.json").write_text(json.dumps({"acts": [{
        "id": "a_1900", "title": "Act A", "year": 1900, "status": "in_force", "source": {},
        "sections": [{"num": "5", "title": "x", "text": "body five"},
                     {"num": "5", "title": "dup", "text": "stray duplicate"},
                     {"num": "6", "title": "y", "text": "body six"}]}]}), encoding="utf-8")
    (d / "z_1901.fulltext.json").write_text(json.dumps({"acts": [{
        "id": "z_1901", "title": "Act Z", "year": 1901, "status": "in_force", "source": {},
        "sections": [{"num": "1", "title": "z", "text": "act z body"}]}]}), encoding="utf-8")

    orig_ft, orig_corpus = vs.FULLTEXT_DIR, vs.CORPUS_DIR
    vs.FULLTEXT_DIR = d
    vs.CORPUS_DIR = d / "empty"; (d / "empty").mkdir()
    try:
        vs._seed_collection(FakeCol())     # must NOT raise
    finally:
        vs.FULLTEXT_DIR, vs.CORPUS_DIR = orig_ft, orig_corpus

    ids = captured.get("ids", [])
    assert len(ids) == len(set(ids)), "ids were not de-duplicated"
    assert any(i.startswith("z_1901") for i in ids), "act after the duplicate was dropped"
    assert sum(1 for i in ids if i.startswith("a_1900_s5")) == 1   # first-wins


# ── Glued section starts (`glued_starts`, opt-in) ───────────────────────────────
def test_glued_starts_recovers_body_sections_only_when_opted_in():
    """India Code prints some acts' section starts GLUED to the number in the BODY
    ("73.Compensation for loss…") while the table of contents prints them spaced. The
    strict pattern matched the TOC and missed the body, so the Contract Act kept only 98
    of 238 sections — s.73 (compensation for breach) among the losses.

    Opt-in per act, mirroring `chain_loose_starts`: applied globally, any body line shaped
    "NN.Capital" would open a spurious section, and the default segmenters have no chain
    constraint to catch that.
    """
    import app.ai.ingest_statutes as ing

    pages = [_page([
        "1. Short title.—This Act may be called the Test Act and extends to the whole "
        "of India, coming into force on such date as the Government may appoint.",
        "2. Definitions.—In this Act, unless the context otherwise requires, the terms "
        "used shall carry the meanings assigned to them by this section throughout.",
        "73.Compensation for loss or damage caused by breach of contract.—When a contract "
        "has been broken, the party who suffers is entitled to receive compensation for "
        "any loss or damage caused to him thereby which naturally arose in the usual course.",
        "The rate shall be 100.5 per cent of the amount in default under this provision.",
    ])]

    old = ing._GLUED_STARTS
    try:
        ing._GLUED_STARTS = False
        strict = {s["num"] for s in _segment_sections(pages)}
        assert "73" not in strict, "glued start recovered without the opt-in flag"

        ing._GLUED_STARTS = True
        secs = {s["num"]: s for s in _segment_sections(pages)}
        assert "73" in secs, "glued start not recovered with the flag on"
        assert "Compensation for loss" in secs["73"]["text"]
        # the decimal must never open a section, flag or no flag
        assert "100.5" not in secs
        assert "100.5 per cent" in secs["73"]["text"], "decimal line left its parent section"
    finally:
        ing._GLUED_STARTS = old


def test_spaced_footnote_bracket_is_recognised_globally():
    """"1 [53A. Part performance" — the amendment footnote is printed both adjacent
    ("2[304B.") and spaced. Requiring adjacency lost Transfer of Property s.53A. A footnote
    digit followed by "[" is unambiguous, so this needs no opt-in."""
    from app.ai.ingest_statutes import _START_RE

    m = _START_RE.match("1 [53A. Part performance.—Where any person contracts to transfer")
    assert m and m.group(1) + m.group(2) == "53A"
    # the adjacent form IPC 304B depends on must still work
    m2 = _START_RE.match("2[304B. Dowry death.—Where the death of a woman is caused")
    assert m2 and m2.group(1) + m2.group(2) == "304B"


# ── Schedule provenance: cited page must be the real page ───────────────────────
def test_schedule_article_pages_are_absolute_not_schedule_relative():
    """A Schedule article must cite the page it is actually printed on.

    `_flat_lines` numbers pages from 1 within whatever list it receives, and
    `_segment_with_schedule` hands it a SLICE beginning at the Schedule. Schedule articles
    therefore recorded a page relative to the Schedule: the Commercial Courts Act cited its
    Order XI rules as "pages 4-8" when they are physically on pages 14-18.

    Provenance is the whole point of this corpus — an advocate verifying a provision turns
    to the page we cite. A wrong page silently breaks that, and no count-based check can
    see it.
    """
    pages = [
        _page(["PRELIMINARY", BODY[1]]),          # p1
        _page([BODY[2]]),                          # p2
        _page(["THE SCHEDULE", "(See section 16)"]),   # p3  <- schedule starts here
        _page(["1. Disclosure of documents.—Plaintiff shall file a list of all documents "
               "and photocopies in its power, possession, control or custody, pertaining "
               "to the suit, along with the plaint."]),                       # p4
        _page(["2. Discovery by interrogatories.—In any suit the plaintiff or defendant "
               "may apply for leave to deliver interrogatories in writing for the "
               "examination of the opposite parties."]),                      # p5
    ]
    import app.ai.ingest_statutes as ing
    old = ing._BARE_SCHEDULE
    try:
        ing._BARE_SCHEDULE = False                 # "THE SCHEDULE" form
        secs = ing._segment_with_schedule(pages)
    finally:
        ing._BARE_SCHEDULE = old

    sched = {s["num"]: s for s in secs if str(s["num"]).startswith("Sch.")}
    assert sched, "no schedule articles parsed"
    for num, s in sched.items():
        page = s.get("page")
        assert page, f"{num} has no page"
        probe = " ".join(s["text"].split())[:40].lower()
        actual = " ".join(pages[page - 1].split()).lower()
        assert probe in actual, (
            f"{num} cites page {page}, but its text is not on that page — the page is "
            "relative to the Schedule instead of the PDF")
    # and specifically: articles are on pages 4/5, never 1/2
    assert min(s["page"] for s in sched.values()) >= 4
