# Corpus Limitations & Governed Edge Cases (Phase 5)

**Built:** 2026-07-21 · corpus fingerprint `2965aab084ff` · 50 acts / 8,442 provisions / 8,646 chunks.

Structured record of what the corpus does NOT fully cover, and how each limitation is disclosed,
tested, and governed. "Acquisition queue empty" means the *selected* ingestion queue is exhausted
— it does **not** mean the legal corpus is complete for every offered topic. Anything below that
touches a legal-correctness question is `PENDING_LEGAL_REVIEW` and feeds the G1 human gate; the
agent does not adjudicate it.

Live anomaly report: `python -c "import json,app.ai.corpus_updates as c; print(json.dumps(c.corpus_anomalies(),indent=2))"`

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
is gone. Like the NDPS psychotropic schedule, it needs dedicated schedule handling.

`OWNER_QUEUE`: schedule-aware parsing is now required by three acts (NDPS psychotropic
substances, SRA infrastructure, Commercial Courts Order XV-A). It should be built once.

Three are known-mixed and need diagnosis first: `motor_vehicles_1988` (gains s.2, loses
ss.140-144 no-fault liability), `stamp_1899` (gains an 11,191-char s.2, loses ss.62-65),
`ipc_1860 +wrapped_headings` (loses six sections).

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
