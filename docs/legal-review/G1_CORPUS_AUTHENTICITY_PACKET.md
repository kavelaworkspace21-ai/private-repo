# G1 — Corpus Authenticity Sign-off Packet (READY — UNSIGNED)

> **Human gate.** This packet is prepared by the build system for review by a qualified human
> (senior advocate / legal editor). It is **not self-certified**: Gate G1 opens only when the
> reviewer signs below. Prepared 2026-07-17 · refreshed 2026-07-20 (adds the Income-tax
> Rules, 2026 and Income-tax Act, 2025 slices; same-day completeness slice re-ingested
> Limitation/IPC/Evidence and strengthened the fingerprint to also hash parsed content) ·
> corpus version **2965aab084ff**.

## 1. What is being certified
That Juriscite's legal corpus consists of **authentic, verbatim statutory text from official
government sources**, with verifiable provenance, and that its known limitations are honestly
disclosed to users.

## 2. Corpus snapshot
- **50 acts as source-verified full text** · **8,442 sections** ·
  **8,646 embedded chunks** · corpus fingerprint `2965aab084ff` (hashes source sha256 AND
  parsed content — changes iff any verified text changes, including parser-level changes).
- Every section carries: verbatim text, source URL, source SHA-256, page number, fetch date.
- No registry act pending acquisition. The register now includes one subordinate-legislation
  instrument (Income-tax Rules, 2026 — cited "Rule N", from the official Gazette print).

## 3. Methodology (what makes this trustworthy)
1. **Official sources only** — India Code bitstreams; the Income-tax Act 2025 from the Income
   Tax Department's official portal; the Income-tax Rules 2026 from the official Gazette print.
   No scraping, no commentaries, no AI-generated legal text.
2. **Deterministic extraction** — pdfplumber parsing; no LLM anywhere in the ingestion loop.
3. **Landmark-content acceptance** — every act is accepted only after its landmark sections are
   verified by a CONTENT keyword from the actual provision (rule adopted after a caught incident
   where 'Article 21' parsed as a Schedule paragraph; key-presence checks are banned).
4. **Repeal/currency flags** — repealed statutes (IPC/CrPC/Evidence → BNS/BNSS/BSA w.e.f.
   01-07-2024; Income-tax 1961 → ITA 2025 w.e.f. 01-04-2026) are flagged in every citation and
   in the model's grounding instructions.
5. **Drift monitoring** — weekly automated re-download + SHA-256 comparison against official
   bitstreams; drift is reported, never auto-ingested.
6. **Deterministic eval gates in CI** — 15 safety cases (refusal/citation/banned-phrase/intent)
   + 28 high-stakes retrieval cases (bail bars, sanction gates, repeal flags, ITA-2025 charge/
   evasion/repeal-savings, Limitation condonation + Art.137 residuary), 100% must pass.

## 4. Per-act provenance register
| Act | Status | Sections | Median body (chars) | Quality | SHA-256 (12) | Fetched | Source |
|---|---|---|---|---|---|---|---|
| Arbitration and Conciliation Act, 1996 | in_force | 85 | 845 | VERBATIM | `2a4e9f2d5e3a` | 2026-06-25 | India Code |
| Bharatiya Nyaya Sanhita, 2023 | in_force | 356 | 633 | VERBATIM | `ff92dcc72778` | 2026-06-25 | India Code |
| Bharatiya Nagarik Suraksha Sanhita, 2023 | in_force | 530 | 757 | VERBATIM | `8047fe1de609` | 2026-06-25 | India Code |
| Bharatiya Sakshya Adhiniyam, 2023 | in_force | 169 | 544 | VERBATIM | `993882ad0ae7` | 2026-06-25 | India Code |
| Central Goods and Services Tax Act, 2017 | in_force | 126 | 1209 | VERBATIM | `c4dbd51f0355` | 2026-06-25 | India Code |
| Commercial Courts Act, 2015 | in_force | 33 | 689 | VERBATIM | `dea56f8890e2` | 2026-07-17 | India Code |
| Companies Act, 2013 | in_force | 433 | 1435 | VERBATIM | `d6e286d2a3fe` | 2026-06-25 | India Code |
| The Constitution of India | in_force | 684 | 500 | VERBATIM | `bc881e3b5926` | 2026-07-15 | India Code |
| Consumer Protection Act, 2019 | in_force | 100 | 655 | VERBATIM | `414fb1edd9b0` | 2026-06-25 | India Code |
| Indian Contract Act, 1872 | in_force | 98 | 974 | VERBATIM | `d756d45a58c4` | 2026-06-25 | India Code |
| Code of Civil Procedure, 1908 | in_force | 179 | 1014 | VERBATIM | `81a542d54d30` | 2026-06-25 | India Code |
| Code of Criminal Procedure, 1973 | repealed → Bharatiya Nagarik Suraksha Sanhita, 2023 | 497 | 799 | VERBATIM | `5bb6514251a9` | 2026-06-25 | India Code |
| Digital Personal Data Protection Act, 2023 | in_force | 51 | 806 | VERBATIM | `d8d9a3dda426` | 2026-07-16 | India Code |
| Protection of Women from Domestic Violence Act, 2005 | in_force | 37 | 524 | VERBATIM | `65eba6c2b14f` | 2026-06-27 | India Code |
| Indian Easements Act, 1882 | in_force | 63 | 639 | VERBATIM | `1b2a1b27e1c3` | 2026-06-27 | India Code |
| Indian Evidence Act, 1872 | repealed → Bharatiya Sakshya Adhiniyam, 2023 | 184 | 532 | VERBATIM | `62b33659545e` | 2026-07-20 | India Code |
| Family Courts Act, 1984 | in_force | 23 | 741 | VERBATIM | `b78062bf192a` | 2026-07-17 | India Code |
| Guardians and Wards Act, 1890 | in_force | 45 | 613 | VERBATIM | `b9cdae6839d9` | 2026-07-17 | India Code |
| Hindu Marriage Act, 1955 | in_force | 30 | 1114 | VERBATIM | `dbdc6d2a4223` | 2026-07-11 | India Code |
| Hindu Succession Act, 1956 | in_force | 28 | 532 | VERBATIM | `8ee27226825b` | 2026-07-11 | India Code |
| Insolvency and Bankruptcy Code, 2016 | in_force | 260 | 1019 | VERBATIM | `ee251f9934e9` | 2026-06-27 | India Code |
| Industrial Disputes Act, 1947 | in_force | 78 | 1197 | VERBATIM | `0af99b73ac2b` | 2026-07-17 | India Code |
| Income-tax Act, 1961 | repealed → Income-tax Act, 2025 | 791 | 46 | HEADINGS-GRADE — re-verify | `428b1b3cf2c3` | 2026-06-25 | India Code |
| Income-tax Act, 2025 | in_force | 537 | 1598 | VERBATIM | `7db7feb6fa54` | 2026-07-20 | Income Tax Dept (official portal) |
| Income-tax Rules, 2026 | in_force | 333 | 1395 | VERBATIM | `f565e0f5ff3b` | 2026-07-17 | Gazette of India (G.S.R. 198(E)) |
| Indian Succession Act, 1925 | in_force | 327 | 573 | VERBATIM | `fe096024e6c3` | 2026-06-27 | India Code |
| Indian Penal Code, 1860 | repealed → Bharatiya Nyaya Sanhita, 2023 | 578 | 476 | VERBATIM | `ae8920ad726f` | 2026-07-20 | India Code |
| Information Technology Act, 2000 | in_force | 30 | 977 | VERBATIM | `e71725fa32e8` | 2026-06-25 | India Code |
| Juvenile Justice (Care and Protection of Children) Act, 20 | in_force | 110 | 1018 | VERBATIM | `5b0c64d69334` | 2026-07-17 | India Code |
| Legal Services Authorities Act, 1987 | in_force | 38 | 1186 | VERBATIM | `3aae5d5c9f8c` | 2026-07-17 | India Code |
| Limitation Act, 1963 | in_force | 169 | 181 | VERBATIM — complete (32 body + 137 Schedule articles; the overall median is low because Schedule limitation-table rows are inherently short — body-section median is 813) | `1ad1f2964881` | 2026-07-20 | India Code |
| Mediation Act, 2023 | in_force | 61 | 841 | VERBATIM | `79efb88576ca` | 2026-07-17 | India Code |
| Motor Vehicles Act, 1988 | in_force | 216 | 1330 | VERBATIM | `be5bac906607` | 2026-06-25 | India Code |
| Muslim Women (Protection of Rights on Marriage) Act, 2019 | in_force | 8 | 341 | VERBATIM | `e90491fbe24c` | 2026-07-17 | India Code |
| Narcotic Drugs and Psychotropic Substances Act, 1985 | in_force | 116 | 888 | VERBATIM | `8cd8e71f5e1b` | 2026-07-16 | India Code |
| Negotiable Instruments Act, 1881 | in_force | 142 | 397 | VERBATIM | `50fe22a157a2` | 2026-07-11 | India Code |
| Indian Partnership Act, 1932 | in_force | 72 | 582 | VERBATIM | `6fa1e7859290` | 2026-06-27 | India Code |
| Prevention of Money-laundering Act, 2002 | in_force | 73 | 917 | VERBATIM | `d3699f0228f7` | 2026-07-16 | India Code |
| Prevention of Corruption Act, 1988 | in_force | 39 | 1121 | VERBATIM | `57a0d7960125` | 2026-07-16 | India Code |
| Protection of Children from Sexual Offences Act, 2012 | in_force | 41 | 776 | VERBATIM | `def90f072fdb` | 2026-06-27 | India Code |
| Registration Act, 1908 | in_force | 92 | 618 | VERBATIM | `be32e7165b81` | 2026-07-17 | India Code |
| Real Estate (Regulation and Development) Act, 2016 | in_force | 88 | 856 | VERBATIM | `5840ece73e30` | 2026-06-27 | India Code |
| Right to Information Act, 2005 | in_force | 31 | 2304 | VERBATIM | `8956eaba5db4` | 2026-07-11 | India Code |
| Sale of Goods Act, 1930 | in_force | 64 | 606 | VERBATIM | `069ff04276e3` | 2026-06-27 | India Code |
| Securitisation and Reconstruction of Financial Assets and  | in_force | 43 | 1381 | VERBATIM | `e7213c51ab3d` | 2026-06-27 | India Code |
| Scheduled Castes and the Scheduled Tribes (Prevention of A | in_force | 26 | 955 | VERBATIM | `da27a14c6931` | 2026-07-17 | India Code |
| Maintenance and Welfare of Parents and Senior Citizens Act | in_force | 32 | 648 | VERBATIM | `677f1b996d34` | 2026-07-17 | India Code |
| Specific Relief Act, 1963 | in_force | 38 | 833 | VERBATIM | `7b90aae6b01d` | 2026-06-27 | India Code |
| Indian Stamp Act, 1899 | in_force | 151 | 559 | VERBATIM | `80fd54af33dc` | 2026-07-17 | India Code |
| Transfer of Property Act, 1882 | in_force | 107 | 848 | VERBATIM | `5223fdf06a0a` | 2026-06-27 | India Code |

## 5. Known limitations (disclosed, not hidden)
- **Acts flagged non-VERBATIM above (1):** income_tax_1961 — heading-grade, kept for
  historical citation of the repealed Act (pre-2026 tax years); every citation carries the
  repeal flag pointing to the ITA-2025. (The answer layer already marks non-verified text as
  'heading only — exact wording unverified'.) The former limitation_1963 THIN flag is
  resolved: 2026-07-20 re-ingest is complete and verbatim.
- **Repealed-section stubs (2026-07-20):** India Code prints a repealed section as
  "N. [Heading.]—Rep. by …". These stubs are now ingested as sections (Limitation ss.28/32,
  IPC ss.15/58/59/61, Evidence s.2) so section-number lookups resolve honestly instead of
  silently missing; the fix also removed orphaned stub tails that had contaminated the ends
  of IPC ss.57/60.
- **Constitution:** 466 articles + 7th & 10th Schedules verified; Schedules 1-6/8/9/11/12 and the
  abrogated Art. 370 appendix are not yet ingested.
- **Income-tax:** the repealed 1961 Act is heading-grade (flagged repealed — historical
  citations for pre-2026 tax years). The 2025 Act is now source-verified full text (537
  sections = all 536 base numbers + inserted 354A; landmark contents verified incl. s.4
  charge on the "tax year" and s.536 repeal-and-savings).
- **Amendment dates:** citations carry act-level repeal dates, not per-section amendment dates
  (a dedicated ingestion slice; wrong dates are worse than none).
- **Judgments:** no judgment corpus; live case-law links are surfaced read-only and marked
  'good-law status unverified' (owner decision C-04 pending).

## 6. Reviewer checklist
- [ ] Spot-check 10 sections across 5 acts against indiacode.nic.in (verbatim match incl. provisos)
- [ ] Verify the repeal flags state the law correctly (IPC/CrPC/IEA/ITA-1961)
- [ ] Confirm the limitations in §5 are acceptable for the closed beta with the standing disclaimers
- [ ] Confirm refusal behaviour on a question outside the corpus (no source → no answer)

## 7. Sign-off
| Field | |
|---|---|
| Reviewer (name, enrolment no.) | ____________________ |
| Date | ____________________ |
| Verdict (approve / approve-with-conditions / reject) | ____________________ |
| Conditions / notes | ____________________ |
