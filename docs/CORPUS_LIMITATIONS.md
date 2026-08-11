# Corpus Limitations & Governed Edge Cases (Phase 5)

**Built:** 2026-07-21 · corpus fingerprint `2965aab084ff` · 50 acts / 8,442 provisions / 8,646 chunks.

Structured record of what the corpus does NOT fully cover, and how each limitation is disclosed,
tested, and governed. "Acquisition queue empty" means the *selected* ingestion queue is exhausted
— it does **not** mean the legal corpus is complete for every offered topic. Anything below that
touches a legal-correctness question is `PENDING_LEGAL_REVIEW` and feeds the G1 human gate; the
agent does not adjudicate it.

Live anomaly report: `python -c "import json,app.ai.corpus_updates as c; print(json.dumps(c.corpus_anomalies(),indent=2))"`

---

## ✅ RESOLVED 2026-08-08 — a footnote filter was deleting real section headings

**Indian Succession Act ss.30 and 90 were absent, and 65 sections across the corpus were
recovered by the same fix.** Found by rebuilding all 50 acts from source — not by any test.

`_FOOTNOTE_RE` drops a line whose first word after the number is an editorial opener
(`Subs.`, `Ins.`, `See`, `As to`, `Words`, …). Two ISA sections genuinely OPEN with those
words:

| Section | Opens with | Absorbed into |
|---|---|---|
| s.30 *As to what property deceased considered to have died intestate* | "As to" | s.29 |
| s.90 *Words describing subject refer to property answering description at testator's death* | "Words" | s.89 |

Both were removed before segmentation ever ran, so neither was addressable by its own number
and each one's text silently extended its predecessor.

**Fix:** the section-heading guard now applies to BOTH footnote patterns, not only
`_FOOTNOTE_RE2`. A heading is distinguishable from a footnote by SHAPE — `N. <marginal
heading>.—<body>` — not by first word. No India Code footnote has that form; "1. Subs. by Act
3 of 1951, s. 3 and the Schedule." has no `.—` separator at all.

### Why no test caught it, and what that means

This defect was **not introduced by the change that exposed it**. It had been live in the
parser since those openers were added; HEAD's committed corpus file predated that change and
was never rebuilt. **The artifact on disk was correct while the code that generates it was
not.**

No test in this repository could have seen it. Every corpus test reads the shipped JSON. The
only thing that surfaces this class of drift is re-deriving the corpus from source, and that
happened here by accident, because an unrelated `_START_RE` fix forced a full rebuild.

> **✅ ADDRESSED 2026-08-09 — in two parts, because the obvious version cannot run.**
>
> The obvious fix is a CI job that reparses all 50 acts and diffs against the committed
> fulltext. **That cannot run on a GitHub-hosted runner.** It needs `data/source_pdfs/`, which
> is 154 MB across 51 files and gitignored — and `income_tax_2025.pdf` alone is **106 MB**,
> past GitHub's 100 MB per-file limit, so it cannot be committed even if that were wanted.
> Re-downloading in CI is not an option either: some sources are WAF-protected (§6 below).
>
> So the protection is split:
>
> **1. `scripts/verify_corpus_rebuild.py` — the real check.** Re-derives each act from its
> source PDF and compares provision by provision: number, title, text, source page. Runs
> wherever the PDFs live. Restores the working tree on exit, ignores the `fetched_on` stamp
> (nested inside `source`, and it changes every run), and shards for parallelism.
>
> ```bash
> python scripts/verify_corpus_rebuild.py --all --stamp    # ~2 hours
> python scripts/verify_corpus_rebuild.py --skip-slow      # ~33 min, omits income_tax_2025
> ```
>
> Timing is dominated by one act: `income_tax_2025` takes **75–95 minutes**, roughly three
> quarters of a full rebuild, because its source PDF is 106 MB. Sharding does not help — it is
> one indivisible act — hence `--skip-slow` for a fast pass.
>
> **2. `tests/test_corpus_freshness.py` — the part CI enforces, in milliseconds.**
> `PARSER_FINGERPRINT.json` (repo root) records the sha256 of the parser that built the
> committed corpus; the test fails if `app/ai/ingest_statutes.py` no longer matches.
>
> **What each does and does not prove.** The fingerprint proves the corpus was produced by a
> parser with that exact hash. It does **not** prove the parse is correct, and it will not
> notice a source PDF being replaced — only a real rebuild shows that. Its narrower job is to
> make *"someone changed the parser and forgot to rebuild"* impossible to miss, which is
> precisely the failure that hid ss.30 and 90.
>
> The test is deliberately strict: **any** edit to the parser trips it, including a comment.
> That is the honest position — you cannot know a change is semantically inert without
> rebuilding, and being wrong here means shipping text that is not the law.
>
> **Still open:** no automated full rebuild. It requires either a self-hosted runner with the
> PDFs, or durable object storage for them (owner action — agent AWS access is revoked). Until
> then the full rebuild is a documented manual step, run before re-stamping.

### Recovered as a side effect (verified as real provisions, not fragments)

The same rebuild — with the `_START_RE` fix for amendment markers followed by a space — added
sections across the corpus, every sampled one a complete provision with heading and body:

| Act | Was → now | Notable recoveries |
|---|---|---|
| `cgst_2017` | 126 → 190 | s.20 ISD credit distribution, s.44 annual return, s.68 inspection of goods in movement |
| `indian_succession_1925` | 327 → 392 | ss.30, 90, plus ss.46, 56, 145, 234 |
| `negotiable_instruments_1881` | 142 → 154 | **s.6 — the definition of "cheque"** |
| `hindu_marriage_1955` | 30 → 37 | **s.16 legitimacy of children of void marriages**, s.13A, s.21A, s.28 |
| `registration_1908` | 92 → 96 | repealed-section stubs |

---

## ✅ RESOLVED 2026-08-08 — the CPC First Schedule (Orders I–LI) is in the corpus

**708 rules across 58 Orders, in a two-level `Ord.<roman>.R.<rule>` namespace.** This closes
the gap opened on 2026-08-05, when `body_before_schedule` correctly cut the Schedule away
from the Code's 158 sections and nothing picked it back up (see "What is still missing"
below, now superseded).

This is most of the civil procedure an advocate cites daily. Order VII Rule 11 (rejection of
plaint), Order VI Rule 17 (amendment of pleadings), Order XXXIX Rules 1–2 (temporary
injunctions), Order IX Rule 13 (setting aside an *ex parte* decree), and the whole of Order
XXI (execution, 114 rules) were **absent from the corpus entirely** until this change.

**Why the generic `Sch.*` machinery could not do it.** `_schedule_regions` finds exactly ONE
region in the whole Code, mislabelled "II", and emits pages 338–347 as a single 34,998-char
blob. Rules renumber from 1 inside every Order, so flattening 58 Orders into one entry
namespace makes 58 competing "entry 1"s — the duplicate-id collision that aborted the seed
and silently dropped 12 acts on 2026-07-12. Hence a dedicated segmenter.

**Four print pathologies had to be handled to get the rules out intact:**

| Symptom | Cause | Effect if unfixed |
|---|---|---|
| Order XV, XV-A, XVI-A, XX-A, XXVII-A, XXXII-A missing | headings carry amendment markers — `*[ORDER XV`, `1[ORDER XVI A` | six Orders absent |
| Order X Rule 3 filed as rule 13 | `1[3.` extracted as `13.` | "Substance of examination to be written" unreachable by citation |
| Order XX Rule 1 missing entirely | printed `1[ 21.` — a space after the marker bracket, which `_START_RE` did not allow | "Judgment when pronounced" absorbed into the heading above it |
| Appendices A–I nearly ingested as rules | specimen plaints are numbered `1.`, `2.`, `3.` | model pleading forms would enter the corpus as law |

The `1[ 21.` fix (one `\s*` in `_START_RE`) also recovered Order XVIII rules 5 and 13.

**Two Orders XI are in force and both are kept.** The Commercial Courts Act 2015 inserted a
separate Order XI (disclosure and discovery before a commercial division) carrying the same
number as the original. They are different law; the second is filed as `Ord.XI-COM.*` so it
cannot overwrite the first.

**Remaining absences are correct**, and asserted as such so a future "fix" cannot re-insert
repealed text as live law: Order XXI rules 60–63 and 70 (omitted by the CPC (Amendment) Act
1976, s. 72) and Order XLI rule 7 (repealed). Every other Order numbers 1..N with no holes.

**Not ingested, and deliberately:** Appendices A–I (pleading, process and decree *forms*) and
the Second Schedule (repealed in 1940). Forms are drafting precedents, not law.

Body sections are **byte-identical** across this change (171 entries, 0 changed).
Pinned by `tests/test_cpc_orders.py` (18 tests, content-based).

---

## ✅ RESOLVED 2026-08-08 — Mediation Act schedules, and three defects found doing it

Enabling the `Sch.*` namespace for `mediation_2023` surfaced three further defects. Each one
**passed a section count**, which is why none was caught earlier.

1. **Schedule I was absent.** `_schedule_regions` scanned only the first 20 lines of each
   page; the Act runs out of s.65 straight into "THE FIRST SCHEDULE" mid-page, so the heading
   was never seen and the act was indexed from Schedule II onwards. Schedule I is the Act's
   own list of **disputes not fit for mediation** — 13 entries, now present.
2. **Widening that scan swept the body INTO the schedule.** Because the heading sits mid-page,
   taking the whole page put ss.55–65 inside Schedule I and re-emitted them as `Sch.I.55` …
   `Sch.I.58`. Fixed by carrying the heading's *line* offset, not just its page.
3. **ss.61 and 62 held the Arbitration Act's text.** The Sixth Schedule substitutes new
   ss.61–62 into the Arbitration and Conciliation Act 1996; the body segmenter reached into
   the schedule and took those as the Mediation Act's own, displacing "Amendment of Act 26 of
   1996" and "Amendment of Act 27 of 2006". **Both neighbours on either side (ss.58–60 and
   ss.63–65) were correct** — the signature of a defect no count can see.
4. **The Statement of Objects and Reasons was ingested as `Sch.X`.** The last schedule region
   ran to end-of-document, so the bill's explanatory note — signed by the minister who moved
   it, describing what the bill "seeks to" do — became `Sch.X.2/3/4`. `Sch.X.4` read "The Bill
   seeks to achieve the above objectives. KIREN RIJIJU." Now excluded by a back-matter
   terminator, and `Sch.X` is the real Tenth Schedule (Consumer Protection Act 2019).

**Caught in passing:** the same back-matter and body-boundary fixes removed two chemical-name
rows that NDPS was carrying as "sections 110H and 110K" (the NDPS Act ends at s.83), and
recovered Partnership Act s.3 ("Application of provisions of Act 9 of 1872"), which had been
glued onto s.2.

Pinned by four content tests in `tests/test_schedule_parsing.py`.

---

## ✅ RESOLVED 2026-08-07 (S7 Workstream D) — Mediation Act: ss.49, 55, 58, 59 recovered

**Every section of ss.1–65 is now present.** Four were absent, from two unrelated causes.

### ss.58 and 59 — a footnote filter firing on a real heading

`_FOOTNOTE_RE2` drops a line if a statutory citation appears anywhere in its first 120
characters. That is right for a footnote block and wrong for a heading that legitimately cites
an Act:

```
58. Amendment of Act 9 of 1872.—The Indian Contract Act, 1872, shall be amended …
59. Amendment of Act 5 of 1908.—The Code of Civil Procedure, 1908, shall be amended …
```

Both were dropped. **s.60 survived only because its heading reads "Amendment of 39 of 1987"
and omits the word "Act".** A parser whose output turns on that is flipping a coin.

Fixed with a structural guard: a SECTION prints `N. <marginal note>.—<body>`; a footnote never
does. `_drop_footnotes` now keeps a line matching that shape even when `_FOOTNOTE_RE2` fires.
`_FOOTNOTE_RE` is deliberately left unguarded — it keys on the first word after the number
("Subs.", "Ins.", "Rep."), which no heading begins with. Eight cases unit-checked, including
the bracketed repeal-stub form `28. [Amendment of certain Acts.]—Rep. by …`.

*This is the same false-positive class that removed `income_tax_rules_2026` rule 48 earlier in
this sprint — the third time `_FOOTNOTE_RE2` has eaten a real provision.*

### ss.49 and 55 — wrapped headings, and a rejection that was wrong

Both headings wrap before the em-dash, so `_seg_dash` never opened them:

```
49. Mediated settlement agreement where Government or its, agency, etc., is a
party.—Notwithstanding anything contained in this Act …
```

The registry **explicitly rejected** `wrapped_headings` for this act, recording:

```
glued_starts      s.65 = 4,917 ch   s.64 intact
glued + wrapped   s.65 =   201 ch   s.64 destroyed 9/12 probes, 5,041 -> 120
```

**That rejection was wrong, and the reason is instructive enough that the original note is
kept in the registry.** ss.63, 64 and 65 are one-sentence amending provisions whose substance
lives in a Schedule — ~120 characters is what they are *supposed* to be. s.65's real text is:

> "Amendment of 35 of 2019.—The Consumer Protection Act, 2019, shall be amended in the manner
> specified in the Tenth Schedule."

The other ~4,800 characters were **the Act's own Schedules**, absorbed: the text ran straight
into "THE FIRST SCHEDULE (See section 6)" and continued to the end of the document. So
4,917 → 201 is the *fix*; the "9/12 probes destroyed" were probes matching Schedule text that
s.64 had wrongly swallowed. **Judging a split by size instead of content reads every correct
parent/child separation as a loss.**

Verified by arithmetic: s.48 1,099 → 499 with s.49 at 595 (499+595 ≈ 1,099); s.54 1,204 → 592
with s.55 at 607 (592+607 ≈ 1,199). Clean splits, not losses.

### Also removed: a CPC provision filed under the Mediation Act

`s.89 "Settlement of disputes outside the Court"` (1,867 ch) was being parsed out of the Tenth
Schedule, which *substitutes* CPC s.89. The Mediation Act has no s.89, so a query for
"Mediation Act s.89" returned the Civil Procedure Code's text. Pre-dates this sprint; fixed
with `max_section: 65`.

**Net:** 65 → 68 entries. Gained 49, 55, 58, 59; lost only the bogus s.89.

### ~~Still open~~ — CLOSED 2026-08-08

The Act's **First–Tenth Schedules are no longer in the corpus**. They were previously inside
s.65, which made them unusable (and made s.65 wrong); they are now absent, which is honest but
still a gap. They need the `Sch.*` namespace treatment, as other acts have. Same shape as the
CPC First Schedule Orders.

**Both are now done** — see the two entries at the top of this file. The Mediation schedules
are in the `Sch.*` namespace (31 entries across Schedules I–X) and the CPC Orders in
`Ord.<roman>.R.<rule>`. Doing the Mediation half turned up three further defects that the
section count had hidden, including ss.61–62 holding the Arbitration Act's text.

---

## ⛔ OPEN — Stamp ss.8B/8E/8F/23A: diagnosed, fix found, **deliberately not shipped**

S7 Workstream A. The audit calls this "8-series suffix handling". **The suffix is not the
problem.** ss.8A, 8C and 8D share exactly the same shape — an amendment-bracket prefix and a
letter suffix — and parse fine. Every missing section has a heading that **wraps before the
em-dash**:

```
2[8B. Corporatisation and demutualisation schemes and related instruments not liable to
duty. —Notwithstanding anything contained in this Act ...

2[23A. Certain instruments connected with mortgages of marketable securities to be chargeable
as agreements. — (1) Where an instrument ...
```

`_seg_dash` requires the em-dash on the number's own line, so it never opens them and the text
merges into the preceding section (8B→8A, 8E/8F→8D, 23A→23).

**Two things had to be true to fix it, and only one of them was.** `_seg_dash` *wins* this act
on score (51,513 vs 49,452), so merely adding the wrapped candidate changes nothing — it must
**replace** plain-dash, which is what `wrapped_headings` means. And this act reaches
segmentation through `_segment_with_schedule`, **which did not accept a `wrapped` argument at
all** — so the flag had no route in however the registry was written. That plumbing gap is now
fixed; the flag works on this path.

### Why it is still not enabled

Enabling it **recovers all four** — 8B (1,326 ch), 8E (2,218), 8F (634), 23A (723), each a
clean parent/child split confirmed by arithmetic (8A −1,333 ≈ 8B; 8D −2,866 ≈ 8E+8F; 23 −731 ≈
23A). Exactly what "do not flatten suffix sections into neighbouring base sections" asks for.

**And it breaks s.2.** Measured, not predicted:

| | before | with `wrapped_headings` |
|---|---|---|
| s.2 *Definitions* | 11,191 ch | **611 ch**, truncated mid-list at "(3) 'Bill of exchange payable on demand'" |
| s.1 | 605 ch, "Short title, extent and commencement" | 10,576 ch, titled **"For Report of the Select Committee, see Gazette of India, 1898"** |

The definitions are absorbed into s.1, whose heading becomes a front-matter line. "instrument",
"conveyance" and "duly stamped" stop being retrievable under their own section — and every
stamp question turns on s.2. The registry already recorded the original trade-off as a
deliberate **ACCEPTED COST**; four missing section *keys* whose text still merges into a
neighbour is the smaller harm.

**So the corpus is unchanged** (`corpus_diff` reports "No corpus differences" after the
revert). Recovering both needs the wrapped strategy fixed so it stops opening s.1 on a
front-matter line — real parser work, not a flag. The diagnosis and the exact numbers are here
so that work starts from evidence rather than from the audit's mis-framing.

---

## ✅ RESOLVED 2026-08-05 (S7) — CPC ss.60 and 92 were unreachable by citation

A footnote marker glued to the section number during extraction. India Code prints an
amendment marker immediately before an amended section's number; where it is bracketed
(`8[60.`) the parser already handled it, but where it is bare it merges:

```
59. Release on ground of illness. ...
860. Property liable to attachment and sale in execution of decree.   ← 8 + 60
91. Public nuisances and other wrongful acts affecting the public.
392. Public charities.                                                ← 3 + 92
```

Both provisions were **present, correct and complete** — filed under numbers that do not
exist. An advocate citing CPC s.60 (property liable to attachment) or s.92 (public charities,
the representative-suit provision) found nothing.

**Fix:** `strip_marker_digits`, opt-in per act. The test is arithmetic, not textual — the
number must be implausibly far ahead of the previous section **and** dropping its first digit
must land back in sequence. A genuine jump fails the second condition (150 after 100 strips to
50, which is behind, so it is left alone), which is what stops it renumbering real provisions.
Six cases were unit-checked before re-ingesting.

> It had to be applied to **both** competing strategies. `_segment_sections` scores
> `_seg_dash` against `_seg_monotonic` and keeps the winner; fixing only `_seg_monotonic`
> changed nothing in the shipped corpus because `_seg_dash` was winning. Worth remembering:
> in this parser, a fix that is not in the winning strategy is not a fix.

**Result:** every gained entry was checked and all 17 are genuine CPC sections — ss.18, 44, 48,
60, 67, 85, 92, 95, 99, 99A, 110, 111, 111A, 135A, 154, 155, 156. Only the two bogus numbers
were lost. **All 158 of ss.1–158 now have an entry (was 145), and the act's page-order score
is 1.00 with zero inversions** (0.76 before any of today's work).

### ⛔ OPEN, and NOT a parser defect — `companies_2013` s.37ZA

The text is real law: "Annual general meetings" for Producer Companies, Chapter XXIA inserted
2020. The number should be **378ZA**. **The official India Code PDF itself prints `37ZA.`** —
page 213 reads 378X, 378Y, 378Z, then 37ZA. The parser reproduced the source faithfully.

That 378ZA is meant is arithmetic: 378Z present, 378ZB present, 378ZA absent, and this entry
carries exactly the content that belongs between them — while sorting under "37", which files
it among ss.35–40, a different part of the Act entirely.

**Deliberately not corrected.** Renumbering would make the corpus assert a section number the
official source does not print, which is a claim about what the law says.
`PENDING_LEGAL_REVIEW`, for G1. The owner may reasonably decide to normalise it with recorded
provenance — that is a human call, not the agent's.

---

## ✅ RESOLVED 2026-08-05 (S7) — the CPC corpus was Orders, Rules and Appendix forms

**The Code of Civil Procedure's section corpus was not its sections.** Investigating the five
CPC entries flagged in the S6 finding below showed the problem was not five sections — it was
the whole act.

| Cited as | Held the text of |
|---|---|
| s.1 *Short title, commencement and extent* | "Presidency Small Cause Courts", page 234 |
| s.2 *Definitions* | a **decree form** template, page 290 |
| s.9 *Courts to try all civil suits unless barred* | an **affidavit form** ("The following debts are due to me:"), page 304 |
| s.10 *Stay of suit* | "Deposit of money, etc., in Court" (Order XXIV) |
| s.11 **Res judicata** | "Oral application" |
| s.89 *Settlement of disputes outside the Court* | "Application to set aside sale on deposit" (Order XXI r.89) |

**The phrase "res judicata" did not appear anywhere in the file.** Neither did "courts to try
all civil suits unless barred". Two of the most-cited provisions in Indian civil procedure were
absent from the corpus of a tool built for litigators, while their numbers returned Order/Rule
text that looked exactly like law.

**Cause.** The Code's body is ss.1–158. Everything after is the **First Schedule** — Orders I
to LI, whose Rules renumber from 1 inside *every* Order — and **Appendices A–H** (forms).
With no boundary, those renumbered Rules and forms parsed as sections and overwrote the Code's
own numbering. It is the same failure mode as the IBC Schedules, and the existing
`body_before_schedule` flag fixes it: `(150, 158)` cuts the page range at the body's tail.

**Result, verified by `scripts/corpus_diff.py`:** 179 entries → 156; page range 27–350 → 27–85.

* **Recovered:** ss.1, 2, 9, 10, 11 (res judicata), 89, and twelve sections that were absent
  altogether — 100A, 109, 126, 130, 138, **148A** (caveat), 153A, 21A, **35A** and **35B**
  (compensatory costs / costs for delay), 43, **44A** (execution of foreign decrees).
* **Removed:** 35 entries. Every one was checked; **not a single one was a CPC section.** All
  were Order/Rule headings ("Order against garnishee" = O.XXI r.46B, "Mode of making
  proclamation" = r.67, "Attachment of agricultural produce" = r.44) or Appendix forms.
* Page-order score, the act-level metric added with this fix: **0.76 → 0.97**. (An earlier
  note here claimed 1.00; that was read off the spot-checked sections rather than recomputed.
  0.97 is the measured value — the residual inversions are the mangled-number entries below.)

### What is still missing, stated plainly

* **13 of ss.1–158 have no entry**: 18, 48, 60, 67, 85, 92, 95, 99, 110, 111, 154, 155, 156.
  ss.110/111 and 154–156 were omitted or repealed by amendment and are legitimately absent.
  The rest are **not yet recovered**.
* **s.60 and s.92 exist but under mangled numbers** — `s.860` ("Property liable to attachment
  and sale in execution of decree") and `s.392` ("Public charities"). A footnote marker is
  glued to the section number (`8`+`60`, `3`+`92`). This is the `glued_starts` class and is the
  obvious next fix.
* ~~**The First Schedule Orders and Rules are now NOT INGESTED AT ALL.**~~ **SUPERSEDED
  2026-08-08** — done, as `Ord.<roman>.R.<rule>`; see the entry at the top of this file. 708
  rules across 58 Orders. The warning it carried still stands and is worth keeping: **do not
  simply remove the boundary flag** to get the Orders back. That restores the corruption. The
  Orders are parsed by their own segmenter from the full page range, on the far side of the
  boundary that `body_before_schedule` draws.

---

## ✅ RESOLVED 2026-08-05 (S7) — Companies, Motor Vehicles and the Constitution

The remaining four entries from the S6 finding below are fixed. Two distinct causes.

**Body boundary** — the same defect as the CPC, in two more acts:

| Act | § | Was | Fix |
|---|---|---|---|
| `companies_2013` | s.3 | 196,395 chars of **Schedule III accounting formats** instead of "Formation of company"; 76 section numbers absent | `body_before_schedule: (465, 470)` |
| `motor_vehicles_1988` | s.5 | the **Statement of Objects and Reasons** instead of "Responsibility of owners" | `body_before_schedule: (210, 217)` |

Companies: 433 → 456 entries, **16 previously-absent sections recovered**, largest section
196,395 → 30,750 chars (s.2 Definitions, genuine), page range now 16–252. Motor Vehicles: 250
entries unchanged, page range 9–118.

**Footnote apparatus parsed as headings** — Constitution Arts 2 and 4:

India Code prints, in the footnote blocks at the bottom of pages 119 and 84:

```
2. Proviso omitted by ibid.
4. Proviso omitted by s. 11, ibid.
```

`_FOOTNOTE_RE` already dropped editorial footnotes — `Subs.`, `Ins.`, `Rep.`, `Omitted` and a
dozen more — but **not `Proviso`**. So both lines opened a *section*. `_FOOTNOTE_RE2`, which
keys on a statutory citation, could not catch them either: "Proviso omitted by ibid." carries
no Act or year. Adding `Proviso`, `Cls.` and `Sub-clause` fixed all four articles.

This recovered more than the two articles. **Art 279A (Goods and Services Tax Council) went
453 → 3,910 chars and Art 124 (Establishment and constitution of the Supreme Court) 1,870 →
3,497** — Arts 2 and 4 had been holding their text. Arts 1–4 now sit contiguously on page 23,
as they should.

> An intermediate attempt adding only `Proviso` fixed Art 2 but **broke Art 3**, which had been
> correct: dropping one footnote shifted the segmentation so a later footnote-derived Art 3
> won instead. Recorded because it is the argument against shipping a keyword-list fix on the
> first green result — the list is inherently incomplete, and the failure mode is silent
> substitution of a provision that was previously right.

### Still open in these acts

* **`companies_2013` s.37ZA** — the text is real law (Producer Company "Annual general
  meetings", Chapter XXIA, inserted 2020) but the number should be **378ZA**; a digit was
  dropped. The provision is present and correct yet unreachable by its true citation — the
  same class as `cpc_1908`'s `s.860` (really s.60) and `s.392` (s.92).
* **`income_tax_2025` s.3** — still holds a table fragment titled "More than 1000000", 52,197
  chars. That act parses through `chain_rules`, a different code path from the two fixed here,
  and has not been investigated.

---

## ⛔ OPEN — TEN provisions hold text that is not the law (found 2026-08-04, S6)

> **UPDATE 2026-08-05: nine of the ten are RESOLVED.** The five `cpc_1908` entries and the four
> above are fixed — see the two sections above. **`income_tax_2025` s.3 remains open.**

**Ten sections across five acts contain something other than the provision they claim to be.**
None was detectable by the existing contamination scanner, because none contains amending
language — they contain a Statement of Objects and Reasons, drafting commentary, a decree form,
an affidavit form, accounting standards, and a table fragment.

| Act | § | Should be | Actually contains |
|---|---|---|---|
| `constitution_1950` | Art 2 | Admission or establishment of new States | The **GST Council** provision (Art 279A). Page 119; Arts 1/3/5 are pages 23–24 |
| `constitution_1950` | Art 4 | Laws providing for amendment of the First and Fourth Schedules | Text about the **NJAC** being struck down. Page 84 |
| `companies_2013` | s.3 | Formation of company | **Schedule III accounting standards**, 196,395 chars. 76 section numbers are absent from the act, consistent with a smear that swallowed them |
| `cpc_1908` | s.1 | Short title, commencement and extent | A provision titled "Presidency Small Cause Courts" |
| `cpc_1908` | s.2 | Definitions | A **decree form** template |
| `cpc_1908` | s.6 | Pecuniary jurisdiction | A **pleading template** ("The agreement is uncertain in the following respects") |
| `cpc_1908` | s.9 | Courts to try all civil suits unless barred | An **affidavit form** ("The following debts are due to me:") |
| `cpc_1908` | s.12 | Bar to further suit | **Drafting commentary** on splitting provisions between the Bill and the Rules |
| `motor_vehicles_1988` | s.5 | Responsibility of owners for contravention | A **Statement of Objects and Reasons** |
| `income_tax_2025` | s.3 | *(the s.3 provision)* | A **table fragment**, titled "More than 1000000" |

**Severity.** These are not obscure provisions. CPC s.9 (jurisdiction of civil courts), CPC s.2
(Definitions), Companies Act s.3 (formation of a company) and Constitution Art 2 are cited
constantly. An advocate retrieving any of them receives text that is not the law, presented
exactly like text that is.

**Why the existing checks missed it.** Every prior integrity check asked *is a section-shaped
chunk present?* — counts, coverage, fingerprints, the citation gate — and each of these ten IS
present, of plausible length, and retrieves normally. `test_corpus_contamination.py` asked the
sharper question but only about **amending** text, which none of these is.

**What is now in place** (`tests/test_corpus_integrity.py`) — four structural detectors, none
keyed to a phrase from a specific act:

* a **title that is a footnote fragment** rather than a heading (caught Constitution Arts 2, 4);
* a **body opening with legislative apparatus** — SOR, drafting notes, court forms, accounting
  schedules (caught Companies s.3, CPC ss.2/6/9, MV s.5);
* a **page number that jumps far forward then back** (caught Companies s.3, Constitution Art 2,
  CPC ss.2/12, MV s.5);
* a **length outlier for its act**, reported separately because length alone proves nothing —
  income_tax_1961 s.10 is 127,539 chars and entirely correct. Human triage of that list is what
  found CPC s.1 and income_tax_2025 s.3.

Verified deterministic: replacing Contract Act s.10 with a Statement of Objects and Reasons
fails the suite naming `contract_1872 s.10`.

**Also recorded, not claimed:** three sections show **trailing absorption** — a correct opening
followed by swallowed schedules/forms/appendices: `crpc_1973` s.484 (158,187 chars),
`bnss_2023` s.531 (192,028), `arbitration_1996` s.86 (34,758). `income_tax_1961` s.80GG
(167,968) is suspected of the same — "Deductions in respect of rents paid" is a short provision
— but this has not been confirmed. The provisions themselves are retrievable; the tails are
foreign.

**Status:** `PENDING_LEGAL_REVIEW` and **blocking for G1**. Recovery is parser work (S7). The
tests pin the damage so it cannot grow silently, and `KNOWN_MISPARSED` must be reduced as fixes
land — a test fails if an entry no longer trips a detector, so recovered provisions cannot stay
listed as broken.

---

## ✅ RESOLVED 2026-07-25 — the Income-tax Act corpus was its TABLE OF CONTENTS

**The entire committed `income_tax_1961` corpus was Arrangement-of-Sections headings, not
law.** 791 "provisions" with a median of **46 characters**, every page number inside 1–29 of
an **880-page** PDF.

| Provision | Committed | Actual body |
|---|---|---|
| s.2 Definitions | 12 chars, page 1 | **62,740 chars, page 30** |
| s.139 Return of income | 17 chars, page 16 | **24,495 chars, page 557** |

The act carried `source_verified: True`, so this text was **quotable as authority**. An
advocate asking about filing returns under s.139 would have been shown a 17-character
heading as the operative statutory provision.

**Root cause — a fix that was never applied to an already-poisoned artifact.** The parser
already had a TOC-skip segmentation chooser (`tests/test_ingest_parser.py`, C-01b, added
after IPC s.302 was caught parsing as 22 chars of heading). The Income-tax corpus file
predated that fix and was never regenerated. Nothing compared the two, because the
fingerprint hashes the committed FILE and stays stable while the parser moves on.

**Fixed:** re-ingested → 616 sections, median **1,593** chars, body pages to 878.
`partnership_1932` corrected 72 → 71 in the same pass.

**A correction to an earlier entry in this file.** It previously argued that 791 was the
more accurate figure and that the parser had lost a capability. That was **wrong and
backwards** — 791 was the poisoned count and the decrease to 616 is the correction. The
diagnosis came from noticing that every "lost" section sat in the TOC page range.

**The acceptance rule this invalidates.** A re-ingest gate of "no act may lose sections"
would have permanently blocked this fix, because the fix IS a loss of 175 entries. A
decrease requires an EXPLANATION, not a veto.

**Guarded by** `test_no_act_is_parsed_from_its_table_of_contents` (fails any act whose
median provision text drops to heading length) and
`test_income_tax_1961_has_real_provision_text` (asserts s.2 and s.139 carry real text from
beyond the TOC page range). A sweep of all 50 acts found **no other poisoned act**.

### Status of the acts that gained sections (audited 2026-07-25)

| Act | Finding | Action |
|---|---|---|
| `it_act_2000` | **FIXED 2026-07-25.** Root cause: the print switches from em-dash to EN-dash at ~page 17, so segmentation died at page 16 of 36 and HALF the Act was never in the corpus. Declaring `single_endash` recovers it: 30 → **102** sections, pages 5-16 → **5-35**, and ss.43A / 66 / 66C-66F / 72A go from ABSENT to present. | done |
| `stamp_1899` | **No action.** Run through its own dispatch (`article_schedule: "bare"` → `_segment_with_schedule`) the current parser produces 153 vs 151 committed, **loses nothing**, and s.3/s.17/s.35/s.62/Sch.1 are byte-identical. | none |
| 14 others | Plausible recoveries; **not verified**. | verify act by act |

#### `it_act_2000` — RESOLVED (2026-07-25), after one reverted attempt

**Root cause: the source print changes dash style part-way through.** Sections up to about
page 16 use the em-dash separator ("7. Retention of electronic records.—(1) …"); from page
17 the Gazette amendments use an EN dash ("44. Penalty for failure…–If any person"). The
dash segmentation strategies stopped recognising heading boundaries at that switch, so the
parse died at page 16 of a 36-page PDF.

**Half the Act was therefore never in the corpus** — including s.43A (compensation for
failure to protect personal data), s.66 (computer related offences), ss.66C-66F (identity
theft, cheating by personation, violation of privacy, cyber terrorism) and s.72A
(disclosure in breach of contract): the provisions this Act is mostly consulted for.

The parser already had the `single_endash` flag (it maps ".–" to ".—" in `_normalize`);
`it_act_2000` simply never declared it. The mapping is additive, so the em-dashes on the
early pages are untouched.

| | Before | After |
|---|---|---|
| Sections | 30 | **102** |
| Pages parsed | 5–16 | **5–35** (of 36) |
| s.2 Definitions | 12,720 chars | 8,946 (no longer absorbing ss.3-9) |
| s.43A / 66 / 66C / 72A | **ABSENT** | **present** |

**Verified in both directions.** Total captured text is 108,710 vs 115,515 before, so the
gap was checked rather than assumed: probing three windows of every committed section
against the new parse, **zero** committed sections are entirely absent and only two (s.31,
s.36) match partially. The difference is redistribution — the old s.2 was large *because* it
had swallowed its neighbours.

**How it stayed hidden.** Section count looked plausible, the fingerprint was stable,
`source_verified` was True, and landmark verification passed because it sampled sections in
the first half. The one measurement that would have exposed it: the parse ends at page 16
and the PDF has 36 pages.

<details><summary>The first attempt, reverted (kept for the reasoning)</summary>

The gains are real, but they are **not free**. Attempting the re-ingest:

| | Committed | Re-ingested |
|---|---|---|
| Sections | 30 | 80 (+51, −1) |
| **Total captured text** | **115,515 chars** | **65,384 chars (−43%)** |
| s.2 Definitions | **12,720 chars** | **ABSENT** |
| s.66 computer-related offences | **ABSENT** | 546 chars |
| s.43A compensation for a data breach | **ABSENT** | 1,437 chars |
| s.5 | 3,742 chars | 773 chars |

The lost definitions text is **not relocated** — no section in the new parse contains the
`"unless the context otherwise requires"` lead-in. Ten further sections shrank by more than
10%.

So neither artifact is correct. The committed one holds far more text, including
Definitions, but is missing s.66 and s.43A — two of the most-cited provisions in the Act
(hacking/computer offences and compensation for a data breach). The re-ingested one recovers
those and loses nearly half the Act.

**Trading 50,000 characters of statute, including Definitions, for four sections is not an
improvement.** Reverted. `it_act_2000` needs the parser fixed so it captures both, which is
its own slice of work.

**Lesson (fifth instance of the same mistake).** I had recorded this act as a "VERIFIED real
recovery" after confirming the GAINS were genuine — without ever checking what was LOST. A
one-sided ledger is not verification. Any per-act accept must compare **total captured text**
in both directions, not just the set of section numbers.

That revert was correct on the evidence then available: without `single_endash` the
re-ingest genuinely destroyed 43% of the Act. Revert → diagnose → fix the cause was the
right order.

</details>

**METHOD WARNING — this cost two wrong conclusions.** Any per-act comparison MUST route
through the same dispatch `ingest()` uses, honouring `article_schedule`, `chain_rules`,
`wrapped_headings` and `glued_starts`. Calling `_segment_sections()` directly on an act with
special handling makes it look catastrophically broken: `stamp_1899` appeared to lose 86
entries including all of Schedule I and the penalties chapter. That was entirely an artifact
of bypassing the act's declared configuration.

**A median-length drop is NOT evidence of degradation either.** `it_act_2000` falls
917 → 535 while genuinely improving, because the parser also recovers legitimately short
omitted sections. Counts, medians and page ranges say where to look; only reading the text
decides.

## ✅ RESOLVED 2026-07-25 — silent parser drops (found 2026-07-24)

**The parser silently omits provisions that are plainly present in the source PDFs.** Found
while authoring the Phase 3 evaluation set; each was confirmed by extracting the PDF text and
comparing it against the parsed corpus.

| Act | Provision | What it is | In PDF | In corpus |
|---|---|---|---|---|
| Indian Contract Act 1872 | **s.73** | Compensation for loss or damage caused by breach of contract | ✅ | ❌ |
| Specific Relief Act 1963 | **s.10** | Specific performance of contract | ✅ | ❌ |
| Transfer of Property Act 1882 | **s.53A** | Part performance | ✅ | ❌ |

These are not obscure provisions. **s.73 is the basis of most contract damages claims in
India**; s.53A is heavily litigated in property matters. The Contract Act shows only **98 of
238** sections parsed.

**Why existing safeguards did not catch it.** All three acts carry `source_verified: True` and
passed landmark **content** verification — because the landmarks checked were *different
sections*. Content verification only ever proves what it samples. The corpus fingerprint is
also no protection: it hashes what WAS parsed, so a consistent omission fingerprints as
perfectly stable.

**Product impact.** A question about damages for breach retrieves no authoritative s.73. It
falls through to semantic search over neighbouring sections, so the answer is either weaker
than it should be or grounds on the wrong provision. Since 2026-07-24 the fail-closed citation
gate withholds an answer citing s.73 (it cannot be resolved), which is correct behaviour but
means the gap now surfaces as a *refusal* rather than a wrong answer.

**Guarded by** `tests/test_corpus_coverage.py`: 14 landmark provisions asserted present, and
the three confirmed gaps asserted to *still* be missing so the defect list cannot outlive the
bug — when the parser is fixed and the acts are re-ingested, that test fails and tells you to
remove the entry.

**FIXED 2026-07-25.** Two India Code print pathologies were the cause: section starts glued
to the number in the body ("73.Compensation…", opt-in `glued_starts`) and a footnote bracket
printed with a space ("1 [53A.", now handled globally). Targeted re-ingest of the three acts:

| Act | Before | After | Provision |
|---|---|---|---|
| Indian Contract Act | 98 | **166** | s.73 recovered, 9,624 chars of verbatim text |
| Specific Relief Act | 38 | **41** | s.10 recovered |
| Transfer of Property Act | 107 | **128** | s.53A recovered, 1,312 chars |

Corpus 8,442 → **8,534**; index reseeded to **8,738** chunks; fingerprint `2965aab084ff` →
**`8a82c520a336`**. Verified by CONTENT and by deterministic retrieval
(`retrieve_by_section()` returns s.73 exactly), with the NI 138 / Art 21 / NDPS 37
regressions intact. 729 tests green.

Deliberately TARGETED, not a full re-ingest — see the P0 above for why a 50-act run is
currently unsafe.

**A coverage census across all 50 acts is a signal, not a verdict.** CPC 1908 looked like an
82% gap but ss. 9, 100 and 151 are all present — its numbering includes Orders/Rules, which the
heuristic miscounts. Only PDF-vs-corpus comparison establishes a real defect. Suspect acts not
yet probed: `cgst_2017`, `mediation_2023`, `ndps_1985`, `companies_2013`, `indian_succession_1925`.

---

## ⛔ OPEN — BNSS 2023 s.2 (Definitions) is not retrievable (found 2026-07-25)

**`retrieve_by_section("Section 2 of the BNSS")` returns NOTHING.**

The text is not lost — it was **absorbed into the `s.1` entry**. That entry runs from
page 16, opens mid-sentence ("1st July, 2024, [except the provisions...") and ends with
"...shall have the meanings respectively assigned to them in that Act and Sanhita", which is
the tail of Definitions. The parser did not recognise
`2. Definitions.—(1) In this Sanhita, unless the context otherwise requires,—` on page 16 as
a section start, so ss.1-2 merged.

**Impact.** BNSS s.2 defines "bail", "bail bond", "bond", "cognizable offence",
"investigation", "police report" and "victim". An advocate asking what any of those means
under the new criminal procedure code gets nothing from the authoritative deterministic
path; the query falls through to semantic search. Since 2026-07-25 the fail-closed citation
gate will withhold an answer citing BNSS s.2 rather than serve an unverifiable one — correct
behaviour, but it surfaces as a refusal on a very common question.

**Not fixed.** BNSS parses 530 sections across ss.1-531 with only this one gap, so the
segmentation is otherwise sound. Changing the strategy to rescue s.2 risks regressing the
other 530, which is a dedicated slice of work with its own verification — not a patch to
attach to an unrelated change.

**Related, and NOT a defect:** BNSS coverage reads 62% (pages 16-172 of 279) because pages
173+ are the **First Schedule** (classification of offences: cognizable/bailable/trying
court) and the Second Schedule of Forms. `crpc_1973` omits its First Schedule too, so this
is a longstanding and CONSISTENT scope decision rather than a BNSS regression. It is still a
real gap for criminal practice — the classification table is consulted constantly — and
should be a deliberate acquisition decision, not an accident.

## ✅ RESOLVED 2026-07-25 — BNS 2023 s.2 (Definitions) recovered

Found by the systematic flag sweep, not by anyone noticing. **The Bharatiya Nyaya Sanhita
2023 — the penal code that replaced the IPC — has no s.2 in the corpus.** s.2 defines
"offence", "document", "dishonestly", "fraudulently", "good faith" and the rest of the
vocabulary the whole Sanhita is written in.

Same defect class as BNSS s.2 (fixed 2026-07-25 via `wrapped_headings`): the unwrapped
segmentation strategies swallow the s.2 heading that follows s.1's wrapped commencement
clause.

**But the fix is NOT clean here.** Enabling `wrapped_headings` on BNS:

| | baseline | wrapped_headings |
|---|---|---|
| Sections | 356 | 357 (**gains s.2**, 583 chars) |
| Total text | 364,793 | 362,869 (**−1,924**) |
| s.358 (repeal and savings) | full | **−2,507 chars** |

So it recovers Definitions and damages the repeal-and-savings section. Unlike BNSS — where
the same flag was purely additive (+1 section, +1,072 chars, nothing lost) — this is a
trade, and neither side is acceptable on its own.

**Not applied.** The right fix recovers s.2 without touching s.358, which means
understanding why the wrapped strategy mis-terminates the final section. That is parser
work with its own verification, not a flag flip.

### The sweep's filter was too permissive — recorded so it is not trusted blindly

The sweep's "candidate" rule was *loses no section, loses no section's text, adds a section
or text*. That admitted five candidates across the eight acts it covered before it was
interrupted, and **all five show +1 section with total text FLAT OR FALLING**:

| act | flag | sections | text |
|---|---|---|---|
| `arbitration_1996` | glued_starts | +1 | −7 |
| `bns_2023` | wrapped_headings | +1 | **−1,924** |
| `bsa_2023` | wrapped_headings | +1 | **−935** |
| `constitution_1950` | double_endash | +1 | +427 |
| `hindu_succession_1956` | glued_starts | +1 | −4 |

The text-probe sampled chars 10-70 of each section, so **tail losses slipped through** — s.358
kept its opening and lost its ending. A corrected rule must require total captured text to be
**non-decreasing**, and should diff per-section lengths rather than sampling.

Note the contrast with the four genuine finds: Contract Act **+68 sections** with s.73
appearing, IT Act 2000 **+72 sections** and half the Act. A real recovery has an unmistakable
signature; a +1/−1,924 does not.

**Unswept:** the run was interrupted after `income_tax_1961`. Acts from `income_tax_2025`
onwards alphabetically have not been tested, and the >300-page acts were skipped by design.

## ⛔ OPEN — the flag sweep's candidates need TAIL verification, not just section counts (2026-07-25)

The sweep found 19 flag/act combinations that add sections. **"Zero sections lost" does not
mean nothing was lost** — text can be destroyed *inside* sections that survive.

### `it_act_2000` + `wrapped_headings` — REJECTED

It recovers nine genuinely absent provisions, including **s.67B** (publishing material
depicting children in sexually explicit acts) and **s.69** (interception, monitoring and
decryption powers). It also **destroys** text:

| Section | Change | Probed verdict |
|---|---|---|
| s.68 → s.69/69A/69B | 5,310 → 612 | **redistributed** (0/4 probes missing) |
| s.67 → s.67A/67B | 3,348 → 794 | **redistributed** (0/4 missing) |
| s.70A → s.70B | 2,688 → 574 | **redistributed** (0/4 missing) |
| **s.2 Definitions** | 8,946 → **547** | **DESTROYED — 9/10 probes missing** |
| **s.90** rule-making | 2,286 → 775 | **DESTROYED — 3/4 missing** |

The lost s.2 text includes the definitions of *communication device*, *computer system*,
*computer network* and *data* — the vocabulary the entire Act is written in.

**Not applied.** This is the same trap as the first `it_act_2000` re-ingest attempt: real
recoveries paired with destruction of Definitions. The act needs the gained sections AND
intact s.2/s.90, which is parser work, not a flag flip.

### Why the sweep could not see this

The sweep's filter probes chars 10-70 of each committed section and asks whether that text
still appears somewhere. **s.2 kept its opening 547 characters**, so the probe passed while
8,399 characters of definitions vanished. Head-sampling cannot detect tail truncation.

**Every remaining candidate must be verified the same way before it is applied:** probe the
FULL span of each shrinking section, not its head, and classify each shrink as redistributed
or destroyed. `ipc_1860 +glued_starts` passed this test (all shrinkage traced to the exact
parent→child splits, net −41 chars) and was applied. `it_act_2000 +wrapped_headings` failed
it.

### Remaining queue — all UNVERIFIED at this depth

`partnership_1932`, `mediation_2023`, `pocso_2012`, `sale_of_goods_1930`,
`legal_services_1987`, `bsa_2023`, `arbitration_1996`, `constitution_1950`,
`hindu_succession_1956`.

Verified and applied at full-span depth: `ndps_1985` (ss.23, 24), `sarfaesi_2002` (s.14 +
nine more, flags only safe in COMBINATION), `rera_2016` (s.2, purely additive),
`transfer_of_property_1882` (s.58, s.43 + five more), `specific_relief_1963` (s.28 + four
more). Each carries its measured evidence in the `STATUTE_REGISTRY` comment.

**Definitions sections are a recurring casualty, and that is predictable rather than random.**
Indian statutes conventionally place a commencement clause at s.1 and Definitions at s.2. When
s.1(3) wraps across lines, the unwrapped segmentation strategies swallow the s.2 heading that
follows. That single mechanism accounts for the lost s.2 in `bns_2023`, `bnss_2023`, `rera_2016`
and `ndps_1985`, and is the open diagnosis in `motor_vehicles_1988`. Any act whose s.1
commencement clause wraps should be treated as a candidate before the sweep is consulted.

### Two accepted costs from the 2026-07-29 applications

**`transfer_of_property_1882` — repeal notices dropped (net −2,600 ch).** Full-span probing
shows the deleted text is almost entirely dead-provision metadata: `"[Decree of foreclosure
suit.] Rep. by the Code of Civil Procedure, 1908, s. 156 and V Schedule"` for ss.86-88, and
the equivalent for ss.96, 98 and s.135 (repealed by the Marine Insurance Act, 1963). Recovered
in exchange: s.58 (mortgage definitions and the six mortgage types) and s.43 (feeding the
estoppel). An advocate who searches for a repealed section now gets nothing rather than a
repeal note — a real, small regression, recorded rather than hidden.

**`specific_relief_1963` — the 2018 Infrastructure Schedule is now dropped (−2,855 ch).**
Previously it was not absent but MISFILED: the whole Schedule (transport, ports, shipyards,
road bridges) sat inside s.42, so retrieving "SRA s.42" returned 3,555 characters under the
heading of an injunction provision. Misattributed text is worse than missing text, because
nothing signals to the reader that it is wrong; s.42 is now its correct ~727 ch. But the
Schedule is legally live — it defines "infrastructure project" for s.20A, which bars
injunctions against such projects. s.20A itself survives intact (1,648 ch); only its Schedule
was gone.

**✅ RESOLVED 2026-07-30 — schedule-aware parsing built.** `_segment_schedules()` recovers the
SRA infrastructure categories (`Sch.1.1`–`Sch.1.5`), the NDPS psychotropic list (106 entries)
and Partnership Schedule I (9 fee entries): 120 entries, every body section byte-identical,
no id repeated. Entries are namespaced on the Constitution's `Sch7.L1.*` precedent so a
schedule entry can never occupy a section number.

**Commercial Courts was listed here as a fourth act needing this, and that was wrong.**
`article_schedule: "bare"` already parses it, and better — the shipped corpus carries `Sch.1`
"Disclosure and discovery of documents", `Sch.2` "Discovery by interrogatories", `Sch.3`
"Inspection", i.e. Order XV-A split rule by rule. The claim was inherited and repeated
without anyone opening the file, and surfaced only because a body-integrity check failed and
the failure was diagnosed instead of blamed on the new code.

That cuts both ways and is worth stating once: this project has now been wrong about corpus
content in **both** directions — text believed present that was amending legislation
(arbitration s.16, CrPC s.44, IBC s.6), and text believed missing that was there all along
(Order XV-A). A claim about what the corpus contains is a claim to verify, not inherit.

### A named trap: character-count deltas cannot tell law from table-of-contents

`partnership_1932` was nearly rejected on its measurements. s.17 showed the worst signature
ever recorded by the full-span probe — **12/12 probes gone, 3,308 → 1,030 ch** — which is the
exact signature that correctly condemned `it_act_2000`. It was in fact the single largest
improvement in the act.

The old s.17 was the act's TABLE OF CONTENTS: `"...18. Partner to be agent of the firm.
19. Implied authority of partner as agent of the firm. 20. Extension and restriction..."` —
a run of bare headings with no bodies. s.17's operative text was verified **absent from the
entire old parse**. The flag replaces a ToC fragment with the real provision.

This is the second time table-of-contents material has produced a confidently wrong reading;
the first was `income_tax_1961`, where an entire act's corpus turned out to be its ToC. So it
is recorded as a standing check rather than re-derived a third time:

> **Full-span probing measures how much text disappears, never what.** A large loss is a
> question, not a verdict. Before accepting or rejecting any candidate, print the text that
> would be deleted and read it. Losses fall into at least five classes with opposite
> implications — operative law (reject), repeal notices (minor), schedules (record the gap),
> state appendices (harmless), and table-of-contents runs (the loss is the *improvement*).
> Counting cannot distinguish them.

Three are known-mixed and need diagnosis first: `motor_vehicles_1988` (gains s.2, loses
ss.140-144 no-fault liability), `stamp_1899` (gains an 11,191-char s.2, loses ss.62-65),
`ipc_1860 +wrapped_headings` (loses six sections).

## ✅ RESOLVED 2026-07-30 — amending text was occupying ten real sections in three acts

The most serious corpus defect found so far, and it predates version control: **nine of the
ten affected sections were already wrong at the baseline commit `1b7e99b`** and nobody had
noticed. It was found by accident, while diagnosing a regression in a fourth.

India Code prints amending material in the same PDF as the principal Act. Its clauses
renumber from 1 — `16. In section 31 of the principal Act,—` — so with no boundary they
parse as sections and **collide with the principal Act's numbering**. The genuine provision
loses.

**The failure mode is the dangerous one.** The section exists, has a plausible length, and
retrieves normally. It simply is not the law. Every integrity check the project had —
section counts, coverage, fingerprints, the citation gate — passes cleanly on a corpus in
this state, because each of them asks whether a section is *present*, never whether its text
is *a provision*.

| Act | Section | Held instead |
|---|---|---|
| `arbitration_1996` | s.16 | `In section 31 of the principal Act,—` — replacing **competence-competence** |
| `arbitration_1996` | s.6 | amendment text, 15,926 ch (Administrative assistance) |
| `arbitration_1996` | s.18 | amendment text, 19,140 ch (Equal treatment of parties) |
| `crpc_1973` | s.16 | `Insertion of new section 144A` (Courts of Metropolitan Magistrates) |
| `crpc_1973` | s.38 | `Amendment of section 438` (Aid to person executing warrant) |
| `crpc_1973` | s.44 | `Amendment of Act 45 of 1860` (**Arrest by Magistrate**) |
| `ibc_2016` | s.6 | Companies Act amendment (**who may initiate a CIRP**) |
| `ibc_2016` | s.19 | Companies Act amendment (Personnel to extend cooperation) |
| `ibc_2016` | s.26 | Companies Act amendment |
| `ibc_2016` | s.36 | Companies Act amendment (**Liquidation estate**) |

Two boundary rules were needed, because the appended material differs in kind:

* `drop_extracts_appendix` — cuts at an `EXTRACTS FROM THE ... (AMENDMENT) ACT, YYYY`
  heading. Arbitration (p44), CrPC (p260).
* `body_before_schedule: (lo, hi)` — cuts at the act's own tail sections, for **Schedules
  that amend OTHER enactments**. IBC's Eleventh Schedule rewrites the Companies Act 2013;
  ss.252–255 sit on p139 where `THE FIRST SCHEDULE` begins, so the body survives whole.

It deliberately does **not** reuse `articles_before_schedule`, which forces `wrapped=True`
and would have silently re-segmented an act never verified under it.

`tests/test_corpus_contamination.py` scans the **shipped corpus** — not the parser — because
that is where the damage was visible and where nobody was looking. Expected count is zero.

### The lesson worth keeping

Every check this project had asked *is the section there?* None asked *is this text law?*
A corpus can be complete, fingerprinted, reproducible and fully covered while a provision
quietly says something else entirely. Presence is not authenticity, and only reading the
text distinguishes them.

### Still open, found in passing

* **`ibc_2016` s.9 is ABSENT** — initiation of a CIRP by an *operational creditor*, routine
  practice. Absent at baseline too, so pre-existing rather than caused by this work. Needs
  its own diagnosis.
* The `_START_RE` bracket-prefix fix (ToP s.53A) also recovered **nine real IBC provisions**
  — ss.10A, 12A, 25A, **29A**, 32A, 77A, 235A, 238A, 240A — including the ineligibility bar
  on defaulting promoters. Recorded because that change was briefly mistaken for a pure
  liability after it broke arbitration s.16.

## ⚠️ Stamp Act ss.8B, 8E, 8F, 23A are not addressable by number · `GOVERNED (accepted 2026-07-30)`

`double_endash` recovers the Stamp Act's **s.2 Definitions (11,191 ch)** — *banker, bill of
exchange, instrument, conveyance, duly stamped* — which was absent from the corpus entirely.
Every stamp question turns on those definitions, so its absence was the single worst gap in
the act.

The price: four provisions lose their section **keys**. Their text survives but merges into
the preceding section, so `retrieve_by_section` cannot reach them by number.

| Provision | Now lives inside |
|---|---|
| s.8B — corporatisation and demutualisation schemes | s.8A |
| s.8E — conversion of a bank branch into a subsidiary | s.8D |
| s.8F — assignment of rights in financial assets | s.8D |
| s.23A — mortgages of marketable securities | s.23 |

(Two further "losses" are inert: s.3A `[Instruments chargeable with additional duty.] Omitted`
and s.79 `[Repealed.]`.)

**Why this was accepted when the specific_relief_1963 misattribution was called worse than
absence.** Two distinctions carried it:

1. **Absent text is unreachable; merged text is reachable but imprecisely addressed.** s.2's
   content was in neither the corpus nor the index — no query of any kind could return it.
   s.8B's content is still found semantically, just not pinpointed by number.
2. **The merge keeps related law together.** ss.8A–8F are all stamp-duty exemptions for
   financial instruments, so a reader receiving 8A+8B gets adjacent law on one subject. The
   SRA case served 2,855 characters about ports and shipyards under an injunction heading —
   nothing signalled the mismatch.

`single_endash` was rejected: it recovers the same s.2 but loses 23 sections including the
entire ss.62–75 penalty run. ss.17, 33, 35, 48, 56 and 62–65 are byte-identical here.

**To close properly** this needs the `8`-series suffix handling that `double_endash` breaks,
not a different flag — the same bucket as `it_act_2000` and `legal_services_1987`.

## 1. IPC 354E — duplicate section number (two distinct provisions) · `PENDING_LEGAL_REVIEW`

- **What:** the source carries **two different provisions numbered 354E** — "Sextortion" and
  "Liability of a person present who fails to prevent an offence under s.354/354A-D".
- **Behaviour:** both are preserved in the fulltext (source evidence intact); the vector index
  keeps the **first** deterministically ("Sextortion") and does not embed the second. This is a
  mechanical de-dup (a stray duplicate must never wipe the corpus — see the 2026-07-12 incident),
  **not** a legal decision about which is canonical.
- **Severity:** medium (a user searching IPC 354E sees only one of two provisions).
- **Disclosure:** recorded by `corpus_updates.corpus_anomalies()`; surfaced in the corpus manifest;
  logged at every reseed with a pointer to this file.
- **Tests:** `test_corpus_limitations.py` (records the anomaly + guards against new/undisclosed ones).
- **Owner action:** legal reviewer decides the canonical treatment (which is in force, whether both
  should be retrievable, correct numbering). Feeds G1.

## 2. Limitation Act — "Article N" vs "Section N" collision · `RESOLVED (governed)`

- **What:** body sections (1-32) and Schedule articles (1-137) share low numbers. "5" is both
  s.5 (condonation of delay) and Article 5 (accounts / share of profits).
- **Behaviour:** the deterministic lookup now routes by **citation intent** — "**Article** 5" →
  Schedule article (`Sch.5`); "**Section** 5" → body section; "Section 65" (no body 65) falls
  through to the Schedule article. Absent any keyword, the deterministic path doesn't fire and
  semantic retrieval handles it.
- **Severity:** low now (was medium — silent body-section precedence).
- **Tests:** eval cases `limitation-5-condonation`, `limitation-137-residuary`,
  `limitation-article5-schedule`; both paths exercised separately.

## 3. Income-tax Act 1961 — heading-grade · `GOVERNED (historical only)`

- Repealed by ITA-2025 (w.e.f. 01-04-2026); parsed at heading grade only. Kept for historical
  citation of pre-2026 tax years. Every citation carries the repeal flag → ITA-2025. Not
  citation-grade for verbatim quotation. Owner action: re-ingest citation-grade if pre-2026
  verbatim tax research is required.

## 4. Amendment dates are act-level, not provision-level · `DEFERRED (disclosed)`

- Citations carry act-level repeal/currency dates, not per-section amendment effective dates.
  Date-specific legal research ("the text of s.X as it stood on DATE") is **not** supported.
  Until provision-level effective-date support exists, such questions must be refused or answered
  with an explicit limitation, never with false precision.

## 5. Constitution Schedules 1-6/8/9/11/12 not ingested · `PARTIAL (owner+legal decision)`

- 466 articles + 7th & 10th Schedules are verified; the other Schedules and the abrogated Art. 370
  appendix are not. Owner + legal reviewer decide whether these are required for beta; otherwise the
  excluded scope is disclosed and questions needing them are refused.

## 6. Drift monitoring — WAF-protected / landing-page sources · `GOVERNED (manual-verify record)`

- **ITA-2025** source is WAF-protected → the weekly drift check returns `error` (honest, never
  auto-ingests). **IT Rules 2026** source is a landing page (not a direct PDF) → `skipped_no_pdf`.
- **Implemented:** `check_upstream()` now attaches an honest **`currency`** state to every result.
  An errored/skipped source is `UNVERIFIED` — **never reported current** — until a human records a
  verification via `corpus_updates.record_manual_verification(act_id, reviewer=..., source_sha256=...,
  next_review_days=...)`, which stores `last_verified_at` / reviewer / checksum / `next_review` in
  `app/legal_corpus/manual_verifications.json`. A record past its `next_review` reverts to
  `UNVERIFIED`. The two known sources are seeded as **PENDING** (`last_verified_at: null`) — the agent
  does not fabricate a sign-off it cannot perform.
- **Owner action:** a reviewer confirms each official source is current, then runs
  `record_manual_verification(...)`. Tests: `test_drift_currency.py`.

## 7. No judgment corpus · `DEFERRED_BY_GOVERNANCE (C-04)`

- Indian Kanoon results are read-only links, explicitly "good-law status unverified", and are
  **never** model grounding. A judgment corpus requires owner decision C-04 plus authoritative full
  text, licensing, paragraph pinpoints, court/date metadata, versioning, and good-law review.

---

**Answer-layer contract:** the RAG layer already marks non-verified text as "heading only — exact
wording unverified", fires repeal banners for repealed statutes, and refuses when no source grounds
an answer. The items above extend that honesty to structural/coverage limits. None may be presented
to an advocate as more complete or more current than this record states.
