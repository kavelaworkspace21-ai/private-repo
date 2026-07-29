"""
Provenance-locked statute ingestion.

NO-HALLUCINATION GUARANTEE:
  This pipeline NEVER generates legal text. It reads the OFFICIAL Act PDF that the
  user downloaded from India Code (indiacode.nic.in), extracts the text
  *deterministically* with a PDF parser (no AI/LLM in the loop), and records the
  source URL, the SHA-256 of the exact file parsed, and the page number for every
  section. Only data produced by this pipeline is marked `source_verified=True` and
  may be quoted verbatim by the agent.

USAGE (after downloading the official PDFs into data/source_pdfs/<act_id>.pdf):
    python -m app.ai.ingest_statutes <act_id>     # one act
    python -m app.ai.ingest_statutes all          # every act with a PDF present
    python -m app.ai.ingest_statutes --list       # show registry + download URLs
"""
import os
import re
import sys
import json
import hashlib
import logging
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # SOURCE_PDF_DIR is read at import time — standalone scripts must see .env too

logger = logging.getLogger(__name__)

ROOT        = Path(__file__).parent.parent.parent
# Overridable alongside CHROMA_PATH (see vector_store.py) — the official-PDF archive is
# provenance-critical but large (154 MB+), so the dev copy lives off the app drive.
PDF_DIR     = Path(os.getenv("SOURCE_PDF_DIR") or (ROOT / "data" / "source_pdfs"))
FULLTEXT_DIR = Path(__file__).parent.parent / "legal_corpus" / "fulltext"

# ── Phase-1 statute registry ────────────────────────────────────────────────────
# `source_url` = the official India Code bitstream (the file the user must download).
# `landing`    = the India Code handle page (human-friendly, lists the PDF).
STATUTE_REGISTRY: dict[str, dict] = {
    "bns_2023": {
        "title": "Bharatiya Nyaya Sanhita, 2023", "short": "BNS", "year": 2023,
        "status": "in_force",
        # Same wrapped-heading defect as the BNSS: s.1's commencement clause wraps across
        # lines and the unwrapped strategies swallowed the s.2 heading after it, so s.2 —
        # DEFINITIONS, which defines offence, document, dishonestly, fraudulently and good
        # faith for the whole Sanhita — was absent from the corpus.
        #
        # This flag also SHRINKS s.358 by 2,507 chars, which looks like damage and is not:
        # both parses carry the identical operative text ("Repeal and savings.—(1) The Indian
        # Penal Code (45 of 1860) is hereby repealed…"), and what the wrapped parse drops is
        # parliamentary BACK-MATTER that the unwrapped one had absorbed — the Statement of
        # Objects and Reasons, Notes on Clauses, "AMIT SHAH", the date and a page number.
        # Removing non-statutory text from a provision marked source_verified is a
        # correction, not a loss.
        "wrapped_headings": True,
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/20062/1/a202345.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/20062",
    },
    "bnss_2023": {
        "title": "Bharatiya Nagarik Suraksha Sanhita, 2023", "short": "BNSS", "year": 2023,
        "status": "in_force",
        # s.1(3) ends "...come into force on such date as the Central Government may, by
        # notification in the Official Gazette, appoint." wrapping across lines, and the
        # unwrapped strategies then swallowed the s.2 heading that follows it. s.2 —
        # DEFINITIONS, which defines bail, bail bond, cognizable offence, investigation,
        # police report and victim — was therefore absent from the corpus entirely and
        # unretrievable by number. `_seg_dash_wrapped` already parsed it correctly and even
        # scored HIGHEST (401,967 vs 401,210); it simply was never tried, because the wrapped
        # strategy is opt-in. Verified additive: +1 section, +1,072 chars, nothing lost.
        "wrapped_headings": True,
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/21544/1/the_bharatiya_nagarik_suraksha_sanhita,_2023.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/20099",
    },
    "bsa_2023": {
        "title": "Bharatiya Sakshya Adhiniyam, 2023", "short": "BSA", "year": 2023,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/20063/1/aa202347.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/20063",
    },
    "constitution_1950": {
        "title": "The Constitution of India", "short": "Constitution", "year": 1950,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/15240",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/15240",
        # Articles run 1–395, then the twelve Schedules RENUMBER from 1 and would overwrite
        # low-numbered articles (Sixth Schedule para 21 "Amendment of the Schedule" shadowed
        # Article 21 "Protection of life and personal liberty"). Segment ONLY the pre-Schedule
        # pages: the boundary is pinned by the tail articles 392–395, which nothing in the
        # Schedules/appendices reaches. `max_section` is a belt-and-suspenders cap. The 12
        # Schedules + the abrogated Art. 370 appendix get their own "Sch." slice later.
        "articles_before_schedule": (392, 399),
        "max_section": 395,
        # Also ingest the Seventh Schedule (Union/State/Concurrent Lists) into a Sch7 namespace,
        # and the Tenth Schedule (anti-defection paragraphs) into a Sch10 namespace.
        "seventh_schedule": True,
        "tenth_schedule": True,
    },
    "cpc_1908": {
        "title": "Code of Civil Procedure, 1908", "short": "CPC", "year": 1908,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/2191",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2191",
    },
    "ipc_1860": {
        "title": "Indian Penal Code, 1860", "short": "IPC", "year": 1860,
        # Amendment-inserted sections are printed glued to their number, so they were
        # absorbed into the preceding section instead of parsed as their own provisions.
        # ABSENT from the corpus until 2026-07-25: s.376AB (rape of a woman under twelve),
        # s.376DA (gang rape, under sixteen), s.376DB (gang rape, under twelve) — the 2018
        # Criminal Law Amendment provisions — plus s.174A (non-appearance under a s.82
        # proclamation) and s.379B (snatching with preparation to cause death or hurt).
        # Verified additive: 577 -> 582 sections, ZERO lost, net text -41 chars. The four
        # sections that shrink are exactly the parents the children were split out of
        # (174->174A, 376A->376AB, 376D->376DA/DB, 379A->379B); each keeps its own heading
        # and operative text. ss.302/376/420/304B/498A byte-identical.
        "glued_starts": True,
        "status": "repealed", "repealed_by": "Bharatiya Nyaya Sanhita, 2023",
        "note": "Repealed w.e.f. 01-07-2024 by the Bharatiya Nyaya Sanhita, 2023; the IPC "
                "continues to govern offences committed before that date.",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/2263",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2263",
    },
    "crpc_1973": {
        "title": "Code of Criminal Procedure, 1973", "short": "CrPC", "year": 1973,
        "status": "repealed", "repealed_by": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "note": "Repealed w.e.f. 01-07-2024 by the Bharatiya Nagarik Suraksha Sanhita, 2023; the "
                "CrPC continues to govern proceedings for offences committed before that date.",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/16225",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/16225",
    },
    "evidence_1872": {
        "title": "Indian Evidence Act, 1872", "short": "Evidence Act", "year": 1872,
        "status": "repealed", "repealed_by": "Bharatiya Sakshya Adhiniyam, 2023",
        "note": "Repealed w.e.f. 01-07-2024 by the Bharatiya Sakshya Adhiniyam, 2023; the Evidence "
                "Act continues to apply to proceedings for offences committed before that date.",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/15351",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/15351",
    },
    "contract_1872": {
        "title": "Indian Contract Act, 1872", "short": "Contract Act", "year": 1872,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/2187",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2187",
        # This print glues the body's section starts to the number ("73.Compensation for
        # loss…") while the table of contents spaces them. Without this only 98 of 238
        # sections parsed — s.73 (compensation for breach), the quasi-contract group
        # (ss.68-72) and the whole of Chapter VI were missing from the corpus.
        "glued_starts": True,
    },
    # ── Additional essential acts (download the PDF, save as <id>.pdf, then ingest) ──
    "income_tax_1961": {
        "title": "Income-tax Act, 1961", "short": "Income-tax Act", "year": 1961,
        # REPEALED w.e.f. 01-04-2026 by the Income-tax Act, 2025 (30 of 2025). Kept in the
        # corpus because pending proceedings continue under it (transitional provisions);
        # answers must flag the repeal. The 2025 Act's ingestion is a future dedicated slice.
        #
        # `repealed_by`/`note` were previously present in the committed fulltext JSON but
        # ABSENT here, so the generator could not reproduce its own artifact: a re-ingest
        # silently blanked them and the repeal banner stopped naming the successor Act. That
        # is the same artifact/generator drift that left the Income-tax corpus parsed from
        # its table of contents — only in the opposite direction (the artifact was RICHER
        # than what the code could rebuild). Caught by the ita61 repeal eval.
        "status": "repealed",
        "repealed_by": "Income-tax Act, 2025",
        "note": "Repealed w.e.f. 01-04-2026 by the Income-tax Act, 2025 (30 of 2025); "
                "pending proceedings continue under transitional provisions.",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2435/1/a1961-43.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2435",
    },
    "cgst_2017": {
        "title": "Central Goods and Services Tax Act, 2017", "short": "CGST Act", "year": 2017,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/15689",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/15689",
    },
    "motor_vehicles_1988": {
        "title": "Motor Vehicles Act, 1988", "short": "MV Act", "year": 1988,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1798",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1798",
    },
    "arbitration_1996": {
        "title": "Arbitration and Conciliation Act, 1996", "short": "Arbitration Act", "year": 1996,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/11799",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/11799",
    },
    # ── Batch 2 (2026-06-25): more high-use central acts ──
    "companies_2013": {
        "title": "Companies Act, 2013", "short": "Companies Act", "year": 2013, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2114/3/a2013-18.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2114",
    },
    "consumer_protection_2019": {
        "title": "Consumer Protection Act, 2019", "short": "Consumer Protection Act", "year": 2019,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15256/1/a2019-35.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/15256",
    },
    "rti_2005": {
        "title": "Right to Information Act, 2005", "short": "RTI Act", "year": 2005, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2065/1/A2005-22.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2065",
    },
    "negotiable_instruments_1881": {
        "title": "Negotiable Instruments Act, 1881", "short": "NI Act", "year": 1881, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15327/1/negotiable_instruments_act,_1881.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2189",
    },
    # This print CHANGES DASH STYLE PART-WAY THROUGH. Sections up to ~page 16 use the
    # em-dash separator ("7. Retention of electronic records.—(1) ..."); from ~page 17 the
    # Gazette amendments use an EN dash ("44. Penalty for failure...–If any person"). Without
    # `single_endash` the dash strategies stopped seeing heading boundaries at that switch, so
    # segmentation died at page 16 of 36 — HALF the Act. That is why ss.43A (compensation for
    # a data breach), 66 (computer related offences), 66C-66F and 72A were absent from the
    # corpus entirely. `_normalize` maps ".–" to ".—", which is additive: the em-dashes on the
    # early pages are untouched.
    "it_act_2000": {
        "single_endash": True,
        "title": "Information Technology Act, 2000", "short": "IT Act", "year": 2000, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/13116/1/it_act_2000_updated.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/13116",
    },
    "hindu_marriage_1955": {
        "title": "Hindu Marriage Act, 1955", "short": "Hindu Marriage Act", "year": 1955, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1560/1/A1955-25.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1560",
    },
    "transfer_of_property_1882": {
        "title": "Transfer of Property Act, 1882", "short": "TP Act", "year": 1882, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2338/1/A1882-04.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2338",
    },
    "limitation_1963": {
        "title": "Limitation Act, 1963", "short": "Limitation Act", "year": 1963, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1565/1/a1963-36.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1565",
        # This Act's substance lives in a Schedule of 137 numbered ARTICLES (the limitation
        # periods). Parse the body sections and the Schedule articles separately so the
        # articles aren't mislabelled as sections. See _segment_with_schedule().
        "article_schedule": True,
    },
    "specific_relief_1963": {
        "title": "Specific Relief Act, 1963", "short": "Specific Relief Act", "year": 1963, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1583/1/A1963-47.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1583",
        # Same glued-start print as the Contract Act: s.10 (specific performance) was lost.
        "glued_starts": True,
    },
    "partnership_1932": {
        "title": "Indian Partnership Act, 1932", "short": "Partnership Act", "year": 1932, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2394/1/A1932-9.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2394",
    },
    "sale_of_goods_1930": {
        "title": "Sale of Goods Act, 1930", "short": "Sale of Goods Act", "year": 1930, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2390/1/193003.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2390",
    },
    "hindu_succession_1956": {
        "title": "Hindu Succession Act, 1956", "short": "Hindu Succession Act", "year": 1956, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1713/1/A1956-30.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1713",
    },
    "dv_act_2005": {
        "title": "Protection of Women from Domestic Violence Act, 2005", "short": "DV Act", "year": 2005,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15436/1/protection_of_women_from_domestic_violence_act,_2005.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2021",
    },
    "indian_succession_1925": {
        "title": "Indian Succession Act, 1925", "short": "Indian Succession Act", "year": 1925, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2385/1/a1925-39.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2385",
    },
    "pocso_2012": {
        "title": "Protection of Children from Sexual Offences Act, 2012", "short": "POCSO", "year": 2012,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2079/1/AA2012-32.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2079",
    },
    "sarfaesi_2002": {
        "title": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act, 2002",
        "short": "SARFAESI Act", "year": 2002, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2006/1/A2002-54.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2006",
    },
    "rera_2016": {
        "title": "Real Estate (Regulation and Development) Act, 2016", "short": "RERA", "year": 2016, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15131/1/the_real_estate_(regulation_and_development)_act,_2016.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2158",
    },
    "ibc_2016": {
        "title": "Insolvency and Bankruptcy Code, 2016", "short": "IBC", "year": 2016, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2154/5/A2016-31.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2154",
    },
    # ── Batch 3 (2026-07-16, owner-directed corpus expansion): litigation staples + new laws ──
    "ndps_1985": {
        # s.2's commencement/definitions run wraps, so the unwrapped strategies swallowed the
        # headings that follow it. ABSENT from the corpus until 2026-07-25: s.23 (punishment
        # for illegal import into/export from India or transhipment), s.24 (external dealings
        # in contravention of s.12), plus ss.4, 13, 33, 44, 51, 53, 59, 70, 71.
        #
        # Verified: 116 -> 129 sections, ZERO lost, and every shrinking section probed across
        # its FULL span (head-sampling cannot see tail truncation — that is how the
        # it_act_2000 candidate hid the destruction of its Definitions). Nine of twelve
        # shrinks are clean redistribution; s.2 keeps 28 of 29 probes with its bloat correctly
        # split into the gained ss.4/13. ss.8/20/21/37 byte-identical, so the bail-restriction
        # regression probe is unaffected.
        #
        # KNOWN COST, accepted: the psychotropic-substances SCHEDULE is malformed in BOTH
        # parses — it appears as bogus "sections" 110H/110K holding chemical names — and this
        # flag drops ~3.6k more of that region (s.83 "Power to remove difficulties" is
        # 10,384 chars in the old parse, which is absurd for that provision; it had absorbed
        # the Schedule). Trading a already-broken chemical table for two missing offence
        # provisions is the right way round, but the Schedule needs its own handling.
        "wrapped_headings": True,
        "title": "Narcotic Drugs and Psychotropic Substances Act, 1985", "short": "NDPS Act",
        "year": 1985, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/18974/1/narcotic-drugs-and-psychotropic-substances-act-1985.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1791",
    },
    "poca_1988": {
        "title": "Prevention of Corruption Act, 1988", "short": "PC Act", "year": 1988,
        "status": "in_force", "wrapped_headings": True,   # s.17A heading wraps past the em-dash
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1558/1/A1988-49.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1558",
    },
    "pmla_2002": {
        "title": "Prevention of Money-laundering Act, 2002", "short": "PMLA", "year": 2002,
        "status": "in_force", "wrapped_headings": True,   # s.50 heading wraps past the em-dash
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2036/5/A2003-15.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2036",
    },
    "dpdp_2023": {
        "title": "Digital Personal Data Protection Act, 2023", "short": "DPDP Act", "year": 2023,
        # Penalty SCHEDULE + Statement-of-Objects reuse numbers 4/6 and clobbered the real
        # sections — split at THE SCHEDULE like the Limitation Act.
        "status": "in_force", "article_schedule": True,
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/22037/1/a2023-22.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/22037",
    },
    "commercial_courts_2015": {
        "title": "Commercial Courts Act, 2015", "short": "Commercial Courts Act", "year": 2015,
        # Its SCHEDULE amends the CPC ("2. Discovery by interrogatories" etc.) and clobbered
        # body s.2 (definitions incl. "commercial dispute") — split at the bare 'SCHEDULE'
        # heading ("bare" = this act's heading has no "THE").
        "status": "in_force", "article_schedule": "bare",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2156/1/a2016-04.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2156",
    },
    # ── Batch 4 (2026-07-16, roadmap P1 continuation): litigation + family/labour/property ──
    "scst_1989": {
        "title": "Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, 1989",
        "short": "SC/ST Act", "year": 1989, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15338/1/scheduled_castes_and_the_scheduled_tribes.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1920",
    },
    "jj_2015": {
        "title": "Juvenile Justice (Care and Protection of Children) Act, 2015",
        "short": "JJ Act", "year": 2015, "status": "in_force", "wrapped_headings": True,
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/8864/1/201602.juvenile2015pdf.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2148",
    },
    "mediation_2023": {
        "title": "Mediation Act, 2023", "short": "Mediation Act", "year": 2023,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/19637/1/aA2023-32.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/19637",
    },
    "registration_1908": {
        "title": "Registration Act, 1908", "short": "Registration Act", "year": 1908,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15937/1/the_registration_act%2C1908.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2190",
    },
    "id_act_1947": {
        "title": "Industrial Disputes Act, 1947", "short": "ID Act", "year": 1947,
        "status": "in_force", "wrapped_headings": True,   # s.33's long heading wraps
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/20352/1/the_industrial_disputes_act.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/15191",
    },
    "senior_citizens_2007": {
        "title": "Maintenance and Welfare of Parents and Senior Citizens Act, 2007",
        "short": "Senior Citizens Act", "year": 2007, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/8865/1/200756senior_citizenact.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2033",
    },
    # ── Batch 5 (2026-07-16): family / legal-aid / stamp tail ──
    "family_courts_1984": {
        "title": "Family Courts Act, 1984", "short": "Family Courts Act", "year": 1984,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/16127/1/a1984__66.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1844",
    },
    "legal_services_1987": {
        "title": "Legal Services Authorities Act, 1987", "short": "Legal Services Act", "year": 1987,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1925/1/198739.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/1925",
    },
    "muslim_women_2019": {
        "title": "Muslim Women (Protection of Rights on Marriage) Act, 2019",
        "short": "Muslim Women Act", "year": 2019, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/11564/1/a2019-20.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/11564",
    },
    "guardians_wards_1890": {
        "title": "Guardians and Wards Act, 1890", "short": "G&W Act", "year": 1890,
        "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2318/1/189008.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2318",
    },
    "stamp_1899": {
        "title": "Indian Stamp Act, 1899", "short": "Stamp Act", "year": 1899,
        # SCHEDULE 1 (stamp-duty rate table, entries 1-65) collides with body sections
        # (its entry "17. CANCELLATION" clobbered s.17) — split at the bare heading.
        "status": "in_force", "article_schedule": "bare",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/20095/1/the_indian_stamp_act%2C_1899.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/15510",
    },
    "income_tax_2025": {
        "title": "Income-tax Act, 2025", "short": "ITA 2025", "year": 2025,
        "status": "in_force",
        # India Code has no bitstream yet; the IT Department's official consolidated PDF
        # ("as amended by Finance Act, 2026") is WAF-protected against automated fetches.
        # OWNER STEP: download it in a normal browser and save as
        # data/source_pdfs/income_tax_2025.pdf, then run the ingest slice.
        "source_name": "Income Tax Department (incometaxindia.gov.in)",
        "chain_rules": True, "chain_title_above": True, "chain_loose_starts": True,
        "page_header_lines": ["Income Tax Department",
                              "Ministry of Finance, Government of India"],
        "source_url": "https://www.incometaxindia.gov.in/documents/20117/43006/Income-tax-Act-2025_2026_2026-06-10_03-46-08_691051_en.pdf/b6240d88-c54c-d2b6-04ee-5703d0bcde4f?version=6.0",
        "landing":    "https://www.incometaxindia.gov.in/income-tax-act-2025",
    },
    "income_tax_rules_2026": {
        "title": "Income-tax Rules, 2026", "short": "IT Rules 2026", "year": 2026,
        "status": "in_force",
        # Owner-supplied OFFICIAL Gazette of India print (G.S.R. 198(E), 20-03-2026, CBDT
        # under s.533 of the Income-tax Act 2025; in force 01-04-2026). Provenance = sha256
        # of the ingested gazette file. Gazette uses EN-dash rule separators (".–(1)").
        "source_name": "Gazette of India, Extraordinary (CBDT — G.S.R. 198(E), 20-03-2026)",
        "source_url": "https://www.incometaxindia.gov.in/pages/rules/income-tax-rules-2026.aspx",
        "landing":    "https://www.incometaxindia.gov.in/pages/rules/income-tax-rules-2026.aspx",
        "single_endash": True, "chain_rules": True,
    },
    "easements_1882": {
        "title": "Indian Easements Act, 1882", "short": "Easements Act", "year": 1882, "status": "in_force",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2349/1/A1882-05.pdf",
        "landing":    "https://www.indiacode.nic.in/handle/123456789/2349",
    },
}

# A section starts with: "<num>. <Heading>.—<text>"  e.g. "318. Cheating.—Whoever ..."
# num may carry a letter suffix (e.g. 304A) or be an Article number for the Constitution.
SECTION_START = re.compile(r"^\s*(\d+[A-Z]{0,2})\.\s+(.+)$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _is_official_pdf(path: Path) -> bool:
    """Reject HTML interstitials saved with a .pdf name (India Code anti-bot pages)."""
    with open(path, "rb") as f:
        head = f.read(5)
    return head == b"%PDF-"


_DOUBLE_ENDASH_ACTS = False  # set per-act by ingest(); "––"→"—" broke Evidence when global
_SINGLE_ENDASH = False       # set per-act; gazette prints use ".–(1)" (EN dash) as separator
_CHAIN_TITLE_ABOVE = False   # set per-act; ITA-2025 prints the marginal note ABOVE the number
_CHAIN_HEADER_LINES: tuple = ()  # set per-act; repeating page-header lines to strip
_CHAIN_LOOSE = False         # set per-act; accept glued/spaced section starts inside a chain
_BARE_SCHEDULE = False       # set per-act by ingest(); bare "SCHEDULE" heading (Commercial Courts)


def _normalize(text: str) -> str:
    """
    Repair punctuation lost to the source PDF's font encoding (U+FFFD / '�').
    India Code PDFs encode the em-dash as a double replacement char and curly quotes
    as singles. We only fix punctuation — never legal wording. The original PDF (with
    its SHA-256) and the source link remain the authoritative reference.
    """
    if not text:
        return text
    text = text.replace("��", "—")   # section marginal-note em-dash
    if _SINGLE_ENDASH:
        # Gazette rule separators: "short title and commencement.–(1)" — map ".–" to ".—"
        # so the dash strategies see the heading/body boundary. Tight pattern, opt-in.
        text = text.replace(".–", ".—")
    if _DOUBLE_ENDASH_ACTS:
        # 2023+ Gazette prints (DPDP) write the heading separator as a double EN-dash
        # ("Consent.––(1)"). Global replacement regressed the Evidence Act (183→160
        # sections), so it is opt-in per act via registry flag `double_endash`.
        text = text.replace("––", "—")
    text = text.replace("�", "'")          # curly quote / apostrophe
    return text


def _extract_pages(path: Path) -> list[str]:
    import pdfplumber
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for pg in pdf.pages:
            pages.append(_normalize(pg.extract_text() or ""))
    return pages


_SEC1_RE  = re.compile(r"^\s*(?:\d{1,3}\[)?1\.\s+[\"'A-Z(]")   # body's "1. ..." line (± amend-bracket)
# Section start. Tolerates India Code's amendment-substitution prefix "N[" (e.g. "2[304B. Dowry
# death.—…" means s.304B substituted by footnote 2) — without it, every substituted/inserted
# section (304B, 375, 498A body, …) was invisible to the parser. Base number = group(1)+(2).
# `\d{1,3}\s*\[` — the amendment-substitution footnote is printed both adjacent ("2[304B.")
# and spaced ("1 [53A. Part performance.—"). Requiring adjacency lost Transfer of Property
# s.53A (part performance), which is heavily litigated. Safe to apply everywhere: a
# footnote marker followed by "[" is unambiguous.
_START_RE = re.compile(
    r"^\s*(?:\d{1,3}\s*\[)?(\d{1,3})([A-Z]{0,2})\.\s+(\S.*)$")  # "318. Heading.—body"

# GLUED section starts — "73.Compensation for loss…" with no space after the period. India
# Code prints the same provision spaced in the table of contents and glued in the body, so
# the strict pattern above matched the TOC entry and missed the BODY: the Contract Act kept
# only 98 of 238 sections (losing s.73, compensation for breach) and Specific Relief lost
# s.10 — present in the source PDF, absent from the corpus, while both acts still reported
# source_verified: True.
#
# OPT-IN per act via the registry's `glued_starts`, deliberately mirroring how
# `chain_loose_starts` gates the same pathology for ITA-2025. Applying it globally is
# tempting and wrong: without the chain constraint that guards the ITA-2025 path, any body
# line shaped "NN.Capital" would open a spurious section. Enable it only for acts whose
# source is known to print this way and whose parse has been checked afterwards.
# The `(?=["'(A-Z])` lookahead still keeps decimals out — "100.5 per cent" can never open a
# section — by requiring the body to begin like a statute body.
_START_GLUED_RE = re.compile(
    r"^\s*(?:\d{1,3}\s*\[)?(\d{1,3})([A-Z]{0,2})\.(?=[\"'(A-Z])(\S.*)$")

_GLUED_STARTS = False        # set per-act by ingest(); accept glued section starts


def _match_start(line: str):
    """Strict section-start match, plus glued starts when the act opts in."""
    m = _START_RE.match(line)
    if m is None and _GLUED_STARTS:
        m = _START_GLUED_RE.match(line)
    return m

# ITA-2025 print pathologies (opt-in via `chain_loose_starts`): a handful of section starts
# are glued to the number ("296.63[(1)…", "427.(1)…", "480.If…") or space the number off the
# period ("95 . The provision…") — invisible to _START_RE, so ss.94/95/296/427/443/454/476/478/480
# (incl. the TDS-default and wilful-evasion prosecutions) vanished into the preceding body.
# Accepted ONLY inside the ascending-chain constraint, and only when the body opens like a
# statute body (amend-bracket / "(" / capital / quote) so decimals ("100.5 per cent") and
# running prose can never open a section.
_CHAIN_LOOSE_RE = re.compile(r"^\s*(\d{1,3})([A-Z]{0,2})\s?\.\s*((?:\d{1,3}\[|[(\"'A-Z]).*)$")

# Editorial FOOTNOTE lines (amendment notes) look like "1. Subs. by Act 36 of 1957, s. 3 …".
# They match _START_RE and _SEC1_RE, poisoning segmentation with fake short "sections" and false
# numbering restarts. They are NEVER statute bodies, so they are dropped before segmentation.
# Openers: an India Code footnote's first word after "N." is an editorial verb or a
# cross-reference phrase ("Subs.", "Ins.", "See", "Cf.", "As to", "The Act has been
# extended…"). No real section heading begins this way, so these are safe to drop.
_FOOTNOTE_RE = re.compile(
    r"^\s*\d{1,2}\.\s+(Subs\.|Ins\.|Rep\.|Added|Omitted|Renumbered|Deleted|Earlier|Now\b|See\b|"
    r"Cf\.|Cl\.|As to\b|Certain words|The words?|The word\b|The Act\b|This Act\b|This\b|Ss?\.\s|"
    r"Sub-s|before\b|after\b|Provided\b|Clause\b|Words\b|Inserted|Substituted|Repealed)", re.I)
# Signature: a short-numbered line whose text carries a statutory-citation marker
# (Act/Reg N of YYYY · w.e.f. · A.O. · commencement) is an amendment note, not a section.
# EXCEPT when the number is followed by a bracketed heading — India Code prints a REPEALED
# section's surviving stub as "28. [Amendment of certain Acts.]—Rep. by …", which is a real
# section entry, not a footnote (Limitation ss.28/32 vanished to this filter, 2026-07-20).
# No editorial footnote opens with "[", so the lookahead is structural, not heuristic.
_FOOTNOTE_RE2 = re.compile(
    r"^\s*\d{1,2}\.\s+(?!\[).{0,120}(Subs\. by|Ins\. by|Rep\. by|w\.e\.f\.|\bAct \d+ of \d{4}|"
    r"\bReg\. \d+ of \d{4}|the A\.O\.|Schedule [IVX]|extended to|came into force)", re.I)


def _drop_footnotes(lines: list[tuple[str, int]]) -> list[tuple[str, int]]:
    return [(ln, pg) for (ln, pg) in lines
            if not (_FOOTNOTE_RE.match(ln) or _FOOTNOTE_RE2.match(ln))]


def _derive_title(text: str) -> str:
    """Marginal heading = text up to the first em-dash; else the first short clause."""
    head = re.split(r"\s*—\s*", text, maxsplit=1)[0]
    head = head.strip().rstrip(".")
    if len(head) > 140:                      # no em-dash found; fall back to first clause
        head = text.strip().split(".")[0][:140]
    return head.strip()


def _flat_lines(pages: list[str]) -> list[tuple[str, int]]:
    out = []
    for page_no, page_text in enumerate(pages, start=1):
        for raw in page_text.split("\n"):
            out.append((raw.rstrip(), page_no))
    return out


def _seg_dash(lines: list[tuple[str, int]]) -> list[dict]:
    """Section starts at "N. heading—text" lines (em-dash present); de-dupe by longest."""
    sections, current = [], None
    for line, page_no in lines:
        m = _match_start(line)
        if m and "—" in line:
            if current:
                sections.append(current)
            current = {"num": m.group(1) + m.group(2), "text": m.group(3).strip(), "page": page_no}
        elif current is not None and line.strip():
            current["text"] += "\n" + line.strip()
    if current:
        sections.append(current)
    best: dict[str, dict] = {}
    for s in sections:
        prev = best.get(s["num"])
        if prev is None or len(s["text"]) > len(prev["text"]):
            best[s["num"]] = s
    return list(best.values())


def _seg_dash_wrapped(lines: list[tuple[str, int]]) -> list[dict]:
    """Like _seg_dash, but tolerant of headings that WRAP across lines before the em-dash.

    India Code's Constitution prints long marginal headings that spill onto a second line
    before the '.—' body separator, e.g.::

        72. Power of President to grant pardons, etc., and to suspend, remit or
            commute sentences in certain cases.—(1) ...

    Plain _seg_dash only opens a section when the em-dash is on the SAME line as the
    number, so it silently merged 45 such articles (incl. Art. 72 pardons, Art. 133/135
    appeals, Art. 249-254 Centre-State relations) into the PREVIOUS article — a citation
    bug (a query for Art. 71 would return Art. 72's pardon text). Here a numbered line with
    no em-dash opens a PENDING heading; the em-dash on a later continuation line (before the
    next numbered start) commits it. Offered as one more scored candidate — _seg_score keeps
    it only when it genuinely parses more real bodies (it does for the Constitution)."""
    sections, current, pending = [], None, None

    def commit():
        nonlocal current
        if current:
            sections.append(current)
            current = None

    for line, page_no in lines:
        m = _match_start(line)
        if m and "—" in line:                       # heading + body on one line (normal)
            commit(); pending = None
            current = {"num": m.group(1) + m.group(2), "text": m.group(3).strip(), "page": page_no}
        elif m:                                      # numbered line, em-dash not here yet
            commit()
            pending = {"num": m.group(1) + m.group(2), "head": m.group(3).strip(), "page": page_no}
        elif pending is not None:
            if "—" in line:                          # em-dash arrived → wrapped heading closes
                current = {"num": pending["num"],
                           "text": (pending["head"] + " " + line.strip()).strip(),
                           "page": pending["page"]}
                pending = None
            elif line.strip():                       # still accumulating heading words
                pending["head"] += " " + line.strip()
        elif current is not None and line.strip():
            current["text"] += "\n" + line.strip()
    commit()
    best: dict[str, dict] = {}
    for s in sections:
        prev = best.get(s["num"])
        if prev is None or len(s["text"]) > len(prev["text"]):
            best[s["num"]] = s
    return list(best.values())


def _seg_monotonic(lines: list[tuple[str, int]]) -> list[dict]:
    """Monotonic-number runs; numbering resets to 1 start a new run; keep the run with most text."""
    runs, current_run, current, last = [], [], None, 0

    def close():
        nonlocal current
        if current:
            current_run.append(current)
            current = None

    for line, page_no in lines:
        m = _match_start(line)
        is_start = False
        if m:
            n = int(m.group(1))
            if n == 1 and last >= 1:
                close()
                if current_run:
                    runs.append(current_run[:])
                current_run.clear()
                last = 0
                is_start = True
            elif n > last or (n == last and m.group(2)):
                is_start = True
        if is_start:
            close()
            current = {"num": m.group(1) + m.group(2), "text": m.group(3).strip(), "page": page_no}
            last = int(m.group(1))
        elif current is not None and line.strip():
            current["text"] += "\n" + line.strip()
    close()
    if current_run:
        runs.append(current_run[:])
    return max(runs, key=lambda r: sum(len(s["text"]) for s in r), default=[])


def _seg_score(sections: list[dict]) -> float:
    """Fitness of a candidate segmentation (C-01b).

    Choosing by COUNT poisoned the corpus: a long ARRANGEMENT OF SECTIONS (table of
    contents) parses into hundreds of one-line 'sections' and wins any count contest —
    IPC's s.302 came out as 22 characters of marginal note. Real statute bodies have
    substantial text, so the fitness is MEDIAN body length (robust to a few glue blobs),
    with a gentle count bonus so a full parse still beats a truncated-but-verbose one.
    """
    if len(sections) < 8:                     # too few to be a statute parse
        return 0.0
    lens = sorted(len(s["text"]) for s in sections)
    median = lens[len(lens) // 2]
    # median × distinct-base-number coverage. Median (verbatim substance) kills a
    # table-of-contents parse; coverage (completeness) beats a verbose-but-truncated run
    # — e.g. IPC's dash run has a higher median than the full monotonic run but misses
    # 84 sections incl. s.34/149/304B/375, so median-only chose the incomplete parse.
    coverage = len({re.match(r"\d+", s["num"]).group() for s in sections})
    return median * coverage


def _segment_sections(pages: list[str], *, wrapped: bool = False) -> list[dict]:
    """
    Deterministically split into sections. Candidates come from two strategies (em-dash
    starts / monotonic numbering), each also re-run from every point where numbering
    restarts at "1." — that is where the BODY begins after a table of contents. The
    QUALITY-scored winner is kept (see _seg_score); text is verbatim (punctuation
    normalised); a source link backs every section.

    `wrapped=True` adds the wrapped-heading strategy (_seg_dash_wrapped) to the candidate
    pool. It is OPT-IN because it is a net win only for texts whose headings routinely
    spill past the em-dash onto a second line (the Constitution): for IPC it would merge
    18 bracketed/repealed & state-amendment sections, so ordinary Acts keep the two-strategy
    pool untouched and byte-identical.
    """
    lines = _drop_footnotes(_flat_lines(pages))
    # wrapped == "replace": the act is KNOWN to wrap headings (registry `wrapped_headings`),
    # so the wrapped strategy REPLACES plain-dash — otherwise plain-dash can outscore it
    # while silently merging the wrapped sections (PoCA s.17A, PMLA s.50 were lost that way:
    # the median-based score preferred 32 clean sections over 38 with the recovered ones).
    # wrapped == True: add as an extra scored candidate (the Constitution path).
    if wrapped == "replace":
        candidates = [_seg_dash_wrapped(lines), _seg_monotonic(lines)]
    else:
        candidates = [_seg_dash(lines), _seg_monotonic(lines)]
        if wrapped:
            candidates.append(_seg_dash_wrapped(lines))
    # TOC-skip candidates: the body's own "1. ..." line restarts the numbering.
    anchors = [i for i, (ln, _pg) in enumerate(lines) if _SEC1_RE.match(ln)]
    for i in anchors[1:12]:                   # [0] ≈ whole doc, already covered above
        tail = lines[i:]
        candidates.append(_seg_dash_wrapped(tail) if wrapped == "replace" else _seg_dash(tail))
        candidates.append(_seg_monotonic(tail))
        if wrapped and wrapped != "replace":
            candidates.append(_seg_dash_wrapped(tail))

    chosen = max(candidates, key=_seg_score)
    if not _seg_score(chosen):                # degenerate PDF — keep the old behaviour
        a, b = candidates[0], candidates[1]
        chosen = a if len(a) >= len(b) else b

    out = sorted(chosen, key=lambda s: (int(re.match(r"\d+", s["num"]).group()), s["num"]))
    for s in out:
        s["text"] = s["text"].strip()
        s["title"] = _derive_title(s["text"])
    return out


def _last_article_page(pages: list[str], lo: int, hi: int) -> int | None:
    """Highest page index whose text opens a section numbered in [lo, hi].

    The Constitution's articles run 1→395 and then the twelve Schedules RENUMBER from 1,
    so Schedule paragraphs collide with (and overwrite) low-numbered articles — the Sixth
    Schedule's para 21 "Amendment of the Schedule" was clobbering Article 21 "Protection of
    life and personal liberty". Detecting the article/schedule boundary by the unmistakable
    tail articles (392-395; nothing in the Schedules or appendices reaches this window) lets
    us segment ONLY the pre-Schedule pages, so no Schedule paragraph can shadow an article.
    Content-based, so it survives re-pagination of a re-downloaded PDF."""
    boundary = None
    for i, pg in enumerate(pages):
        for ln in pg.split("\n"):
            m = _START_RE.match(ln.strip())
            if m and lo <= int(m.group(1)) <= hi:
                boundary = i
                break
    return boundary


def _segment_with_schedule(pages: list[str]) -> list[dict]:
    """For Acts whose substance is a Schedule of numbered ARTICLES (e.g. Limitation Act):
    split at the real 'THE SCHEDULE' page, parse body sections and Schedule articles
    separately. Articles are renumbered 'Sch.N' + titled so they never collide with, or
    get mistaken for, the body sections. Falls back to normal segmentation if no Schedule."""
    sched_page = None
    for i, pg in enumerate(pages):
        for ln in pg.split("\n"):
            # 'THE SCHEDULE …' (Limitation). The bare 'SCHEDULE' heading form is OPT-IN per
            # act (_BARE_SCHEDULE, Commercial Courts) — enabling it globally moved the
            # Limitation Act's split point (137→167 sections) because its PDF also carries
            # a bare 'SCHEDULE' line after the real heading.
            if (re.match(r"^THE\s+SCHEDULE\b", ln.strip(), re.IGNORECASE)
                    or (_BARE_SCHEDULE
                        # bare 'SCHEDULE' (Commercial Courts) or 'SCHEDULE 1/I' (Stamp Act)
                        and re.match(r"^SCHEDULE\s*[I1]{0,3}\.?\s*$", ln.strip(), re.IGNORECASE))):
                sched_page = i  # keep the LAST one (the real Schedule, not the TOC entry)
    if sched_page is None or sched_page == 0:
        return _segment_sections(pages)

    body = _segment_sections(pages[:sched_page])
    articles = _seg_monotonic(_drop_footnotes(_flat_lines(pages[sched_page:])))
    for a in articles:
        a["text"] = a["text"].strip()
        a["title"] = "Schedule, Article " + a["num"] + " — " + _derive_title(a["text"])
        a["num"] = "Sch." + a["num"]
        # `_flat_lines` numbers pages from 1 within whatever list it is given, and it was
        # given a SLICE starting at the Schedule. Schedule articles therefore carried a page
        # relative to the Schedule, not to the PDF — Commercial Courts recorded its Order XI
        # rules on "pages 4-8" when they are physically on pages 14-18. Provenance is the
        # point of this corpus: an advocate checking a provision turns to the page we cite,
        # and would have found something else. Shift back to absolute numbering (sched_page
        # is a 0-based index, the relative page is 1-based, so the sum is correct).
        if a.get("page"):
            a["page"] += sched_page
    return body + articles


def _seventh_list_name(line: str) -> tuple[str, str] | None:
    """Map a SEVENTH SCHEDULE List heading to (display name, namespace tag)."""
    l = line.lower()
    if "union list" in l:       return ("Union List", "L1")
    if "state list" in l:       return ("State List", "L2")
    if "concurrent list" in l:  return ("Concurrent List", "L3")
    return None


def _segment_seventh_schedule(pages: list[str]) -> list[dict]:
    """Parse the Constitution's SEVENTH SCHEDULE (Article 246) — the Union / State / Concurrent
    Lists that divide legislative power (among the most-litigated parts of the Constitution) —
    into a separate ``Sch7.L{1,2,3}.<entry>`` namespace so the entries are retrievable without
    colliding with articles (each List renumbers from 1). Entries are number-driven and wrap
    across lines with no em-dash, so each List is segmented on its own slice with the monotonic
    strategy. Returns [] if the Schedule can't be located (never raises)."""
    def _find(pat: str, lo: int = 0, last: bool = False) -> int | None:
        rx = re.compile(pat)
        found = None
        for i in range(lo, len(pages)):
            if any(rx.match(ln.strip()) for ln in pages[i].split("\n")):
                if not last:
                    return i
                found = i
        return found

    # The heading appears twice: once in the ARRANGEMENT (front matter) and once at the real
    # Schedule. Take the LAST 'SEVENTH SCHEDULE' (the content), then the first 'EIGHTH SCHEDULE'
    # after it — no magic page number needed.
    s7 = _find(r"^SEVENTH\s+SCHEDULE\b", last=True)
    if s7 is None:
        return []
    s8 = _find(r"^EIGHTH\s+SCHEDULE\b", lo=s7 + 1)
    sub = pages[s7:(s8 if s8 else s7 + 12)]
    flat = _drop_footnotes(_flat_lines(sub))

    marks: list[tuple[int, str, str]] = []
    for i, (ln, _pg) in enumerate(flat):
        if re.match(r"^List\s+(?:I|II|III)\b", ln, re.IGNORECASE):
            nm = _seventh_list_name(ln)
            if nm:
                marks.append((i, nm[0], nm[1]))
    if len(marks) != 3:                       # layout not as expected — don't guess
        return []

    bounds = [m[0] for m in marks] + [len(flat)]
    out: list[dict] = []
    for k, (_i, name, tag) in enumerate(marks):
        seg = flat[bounds[k] + 1: bounds[k + 1]]
        for s in _seg_monotonic(seg):
            entry = s["num"]
            s["text"] = s["text"].strip()
            s["title"] = f"Seventh Schedule, {name}, Entry {entry} — " + _derive_title(s["text"])
            s["num"] = f"Sch7.{tag}.{entry}"
            s["page"] = s.get("page", 0) + s7   # _flat_lines(sub) numbers from 1 → absolute page
            out.append(s)
    return out


def _segment_tenth_schedule(pages: list[str]) -> list[dict]:
    """Parse the TENTH SCHEDULE (Articles 102/191 — anti-defection) into a ``Sch10.<para>``
    namespace. Its paragraphs (1-8; para 3, the 'split' defence, was omitted by the 91st
    Amendment, 2003) use the em-dash body form, so the wrapped-dash strategy fits. A leading
    footnote marker is stripped ('*7. Bar of jurisdiction of courts.—…' → paragraph 7) so that
    paragraph — the ouster clause read down in Kihoto Hollohan — is not lost. [] if not found."""
    def _match_page(pat: str, lo: int = 0, last: bool = False) -> int | None:
        rx = re.compile(pat, re.IGNORECASE)
        found = None
        for i in range(lo, len(pages)):
            if any(rx.match(ln.strip()) for ln in pages[i].split("\n")):
                if not last:
                    return i
                found = i
        return found

    # Take the LAST 'TENTH SCHEDULE' (the content heading '1[TENTH SCHEDULE', not the TOC entry),
    # then the first 'ELEVENTH SCHEDULE' after it to bound the paragraphs.
    t10 = _match_page(r"^\d*\[?TENTH\s+SCHEDULE\b", last=True)
    if t10 is None:
        return []
    t11 = _match_page(r"^\d*\[?ELEVENTH\s+SCHEDULE\b", lo=t10 + 1)
    sub = pages[t10:(t11 if t11 else t10 + 4)]
    # Strip a leading footnote marker (*, dagger) that precedes a paragraph number.
    flat = [(re.sub(r"^(\s*)[*†‡]\s*(\d)", r"\1\2", ln), pg) for ln, pg in _flat_lines(sub)]
    flat = _drop_footnotes(flat)
    out: list[dict] = []
    for s in _seg_dash_wrapped(flat):
        s["text"] = s["text"].strip()
        s["title"] = "Tenth Schedule, Paragraph " + s["num"] + " — " + _derive_title(s["text"])
        s["num"] = "Sch10." + s["num"]
        s["page"] = s.get("page", 0) + t10   # _flat_lines(sub) numbers from 1 → absolute page
        out.append(s)
    return out


def _segment_chain_rules(pages: list[str]) -> list[dict]:
    """Chain segmentation for RULES gazettes (Income-tax Rules, 2026).

    A 976-page gazette defeats every page-boundary strategy: forms are embedded INLINE,
    tables inside rules carry their own "6./7./8." numbering, an Act section is quoted
    verbatim ("379.—(1) …" inside the DRC rules), and trailing annexures restart at 1.
    The one invariant is that REAL rule numbers ascend 1, 2, 3 … through the document.
    So: accept a numbered start ONLY if it continues the ascending chain (jump cap +30;
    equal number allowed with a letter suffix). Everything that clobbered the first pass
    — table rows at a chain position of ~158, the s.379 quotation, recovery paragraphs,
    annexure restarts — violates the chain and is rejected structurally, no dedup needed.
    Verified on the 2026 gazette: 333/333 rules, zero gaps, all landmark contents correct."""
    flat: list[tuple[str, int]] = []
    headers = set(_CHAIN_HEADER_LINES)
    for pno, pg in enumerate(pages, 1):
        for ln in pg.split("\n"):
            t = ln.rstrip()
            if t.strip() in headers:      # repeating page furniture (ITA-2025 dept header)
                continue
            flat.append((t, pno))
    chain: list[tuple[int, int, str, int, str]] = []
    prev = 0
    for i, (ln, pno) in enumerate(flat):
        m = _START_RE.match(ln)
        if not m and _CHAIN_LOOSE:
            m = _CHAIN_LOOSE_RE.match(ln)
        if not m:
            continue
        n = int(m.group(1)); suf = m.group(2)
        if (prev == 0 and n == 1) or (prev and 0 < n - prev <= 30) or (n == prev and suf):
            chain.append((i, n, suf, pno, m.group(3)))
            prev = n
    out: list[dict] = []
    for k, (i, n, suf, pno, head) in enumerate(chain):
        j = chain[k + 1][0] if k + 1 < len(chain) else min(i + 400, len(flat))
        body = [head] + [flat[x][0].strip() for x in range(i + 1, j) if flat[x][0].strip()]
        text = "\n".join(body).strip()
        title = _derive_title(text)
        if _CHAIN_TITLE_ABOVE:
            # ITA-2025 print style: the marginal note sits on the line ABOVE the number
            # ("Short title, extent and commencement." then "1. (1) This Act may …").
            for back in range(i - 1, max(i - 4, -1), -1):
                cand = flat[back][0].strip()
                if cand and not _START_RE.match(cand) and cand.endswith("."):
                    title = cand.rstrip(".")
                    break
        out.append({"num": f"{n}{suf}", "page": pno, "text": text, "title": title})
    return out


def ingest(act_id: str) -> dict:
    meta = STATUTE_REGISTRY.get(act_id)
    if not meta:
        raise ValueError(f"Unknown act_id '{act_id}'. Known: {list(STATUTE_REGISTRY)}")

    pdf_path = PDF_DIR / f"{act_id}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Official PDF not found: {pdf_path}\n"
            f"Download it from: {meta['landing']}\n"
            f"and save it as {pdf_path}"
        )
    if not _is_official_pdf(pdf_path):
        raise ValueError(
            f"{pdf_path} is not a real PDF (looks like an HTML page). "
            f"Re-download the actual PDF from {meta['landing']}."
        )

    checksum = _sha256(pdf_path)
    global _DOUBLE_ENDASH_ACTS, _BARE_SCHEDULE
    _DOUBLE_ENDASH_ACTS = bool(meta.get("double_endash"))
    _BARE_SCHEDULE = (meta.get("article_schedule") == "bare")
    global _SINGLE_ENDASH, _CHAIN_TITLE_ABOVE, _CHAIN_HEADER_LINES, _CHAIN_LOOSE, _GLUED_STARTS
    _SINGLE_ENDASH = bool(meta.get("single_endash"))
    _CHAIN_TITLE_ABOVE = bool(meta.get("chain_title_above"))
    _CHAIN_HEADER_LINES = tuple(meta.get("page_header_lines", ()))
    _CHAIN_LOOSE = bool(meta.get("chain_loose_starts"))
    _GLUED_STARTS = bool(meta.get("glued_starts"))
    try:
        pages = _extract_pages(pdf_path)
    finally:
        _DOUBLE_ENDASH_ACTS = False
    if meta.get("chain_rules"):
        sections = _segment_chain_rules(pages)
    elif meta.get("article_schedule"):
        sections = _segment_with_schedule(pages)
    elif meta.get("articles_before_schedule"):
        # Parse ARTICLES only from the pages before the Schedules begin, so Schedule
        # paragraphs (which renumber from 1) cannot overwrite low-numbered articles.
        # The tail articles marked by `articles_before_schedule` (a [lo, hi] window)
        # pin the boundary; Schedules/appendices are a separate later slice.
        lo, hi = meta["articles_before_schedule"]
        end = _last_article_page(pages, lo, hi)
        sub = pages[: end + 1] if end is not None else pages
        sections = _segment_sections(sub, wrapped=True)
    else:
        # `wrapped_headings`: opt-in for Acts whose long headings spill past the em-dash onto
        # a continuation line (PoCA s.17A, PMLA s.50 were silently merged into the previous
        # section without it). Same strategy the Constitution slice uses.
        sections = _segment_sections(
            pages, wrapped="replace" if meta.get("wrapped_headings") else False)
    if not sections:
        raise ValueError(f"No sections parsed from {pdf_path} — check the PDF layout.")

    # Cap the numbering where an Act's provisions end (e.g. Constitution articles end at
    # 395; anything higher in the parse is Schedule/appendix text mis-numbered as a section).
    max_sec = meta.get("max_section")
    if max_sec:
        sections = [s for s in sections
                    if int(re.match(r"\d+", s["num"]).group()) <= max_sec]

    # Append the SEVENTH SCHEDULE's legislative-list entries in their own Sch7 namespace
    # (after the article cap, so the "Sch7.*" ids never hit the numeric cap filter above).
    if meta.get("seventh_schedule"):
        sections = sections + _segment_seventh_schedule(pages)
    if meta.get("tenth_schedule"):
        sections = sections + _segment_tenth_schedule(pages)

    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "acts": [{
            "id": act_id,
            "title": meta["title"],
            "short": meta["short"],
            "year": meta["year"],
            "status": meta["status"],
            # Repeal/currency metadata flows to the citation layer so a repealed provision is
            # never cited without a warning (e.g. IPC → BNS, Income-tax 1961 → ITA 2025).
            "repealed_by": meta.get("repealed_by", ""),
            "note": meta.get("note", ""),
            "source_verified": True,
            "source": {
                "name": meta.get("source_name", "India Code (indiacode.nic.in)"),
                "url": meta["source_url"],
                "landing": meta["landing"],
                "sha256": checksum,
                "fetched_on": date.today().isoformat(),
                "extractor": "pdfplumber (deterministic, no AI)",
            },
            "sections": sections,
        }]
    }
    out_path = FULLTEXT_DIR / f"{act_id}.fulltext.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    logger.info(f"Ingested {act_id}: {len(sections)} sections -> {out_path}")
    return {"act_id": act_id, "sections": len(sections),
            "sha256": checksum, "output": str(out_path)}


def _print_list():
    print("Phase-1 statute registry — download each official PDF and save as "
          "data/source_pdfs/<act_id>.pdf\n")
    for aid, m in STATUTE_REGISTRY.items():
        present = (PDF_DIR / f"{aid}.pdf").exists()
        mark = "PRESENT" if present else "missing"
        print(f"  [{mark}] {aid:18} {m['title']}")
        print(f"             {m['landing']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = sys.argv[1:]
    if not args or args[0] in ("--list", "-l"):
        _print_list()
    elif args[0] == "all":
        for aid in STATUTE_REGISTRY:
            if (PDF_DIR / f"{aid}.pdf").exists():
                try:
                    r = ingest(aid)
                    print(f"OK  {aid}: {r['sections']} sections")
                except Exception as e:
                    print(f"ERR {aid}: {e}")
            else:
                print(f"-- {aid}: no PDF, skipped")
    else:
        r = ingest(args[0])
        print(json.dumps(r, indent=2))
