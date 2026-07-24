"""
Statute-retrieval eval set — high-stakes provisions from the expanded corpus (2026-07-16).

Charter: every case asserts that the DETERMINISTIC retrieval layer serves the RIGHT verbatim
provision (a content keyword from the actual text, never just the section key — the Article-21
"Amendment of the Schedule" incident is why), and that repeal/currency flags fire exactly where
they should. No LLM involved: deterministic, free, runs in CI on every commit.

These provisions are chosen because getting them WRONG harms a client fastest: bail bars
(NDPS 37, PMLA 45, SC/ST 18), sanction/approval gates (PoCA 17A/19), limitation-style windows
(Registration 23/49, ID 25F), and the new-era acts (DPDP consent, Mediation enforcement).
"""

# (id, query for retrieve_by_section, content keyword that MUST appear,
#  expect_repealed_flag — True: "REPEALED" must appear; False: it must NOT)
RETRIEVAL_EVAL_CASES = [
    # ── Bail bars & strict conditions (highest stakes in criminal practice) ──
    ("ndps-37-bail-bar", "Section 37 of the NDPS Act", "bail", False),
    ("pmla-45-twin-conditions", "Section 45 of the PMLA", "bail", False),
    ("scst-18-no-anticipatory", "Section 18 of the SC/ST Act", "438", False),
    ("jj-12-child-bail", "Section 12 of the Juvenile Justice Act", "bail", False),

    # ── Sanction / approval gates ──
    ("poca-17a-prior-approval", "Section 17A of the Prevention of Corruption Act", "approval", False),
    ("poca-19-sanction", "Section 19 of the Prevention of Corruption Act", "sanction", False),

    # ── Offence definitions ──
    ("ndps-20-cannabis", "Section 20 of the NDPS Act", "cannabis", False),
    ("pmla-3-offence", "Section 3 of the PMLA", "money-laundering", False),
    ("scst-15a-victim-rights", "Section 15A of the SC/ST Act", "victim", False),
    ("jj-94-age-determination", "Section 94 of the Juvenile Justice Act", "age", False),

    # ── New-era acts ──
    ("dpdp-6-consent", "Section 6 of the Digital Personal Data Protection Act", "consent", False),
    ("mediation-27-enforcement", "Section 27 of the Mediation Act", "enforce", False),

    # ── Property / labour / family staples ──
    ("registration-49-effect", "Section 49 of the Registration Act", "registered", False),
    ("idact-25f-retrenchment", "Section 25F of the Industrial Disputes Act", "retrench", False),
    ("seniorcit-23-void-transfer", "Section 23 of the Senior Citizens Act", "void", False),

    # ── Limitation Act completeness slice (2026-07-20) ──
    ("limitation-5-condonation", "Section 5 of the Limitation Act", "sufficient cause", False),
    # Art.137 (residuary applications) lived past the old parse's article-106 truncation —
    # pins both the recovered Schedule tail AND the Sch.N deterministic lookup.
    ("limitation-137-residuary", "Article 137 of the Limitation Act", "right to apply", False),
    # Article-vs-Section disambiguation (Phase 5, 2026-07-21): body s.5 (condonation) and
    # Schedule Article 5 (accounts/share of profits) collide on "5". Intent must route them
    # apart — "Article 5" -> the Schedule article ("dissolution"), NOT body s.5.
    ("limitation-article5-schedule", "Article 5 of the Limitation Act", "dissolution", False),
    # s.57 was serving with the orphaned tail of the s.58 repeal stub glued on — the repeal
    # flag must fire (IPC is repealed) but the stub garbage must be gone (pinned in the
    # parser data test; here we pin that the true text serves).
    ("ipc-57-fractions", "Section 57 of the Indian Penal Code", "twenty years", True),
    ("evidence-65b-electronic", "Section 65B of the Indian Evidence Act", "electronic record", True),

    # ── Income-tax Act 2025 (ITA-2025 slice, 2026-07-20) ──
    ("ita25-4-charge-tax-year", "Section 4 of the Income-tax Act 2025", "tax year", False),
    ("ita25-263-return", "Section 263 of the Income-tax Act 2025", "furnish a return", False),
    # s.478 was invisible to the first parse (glued "478.24[(1)…" start) — pins the
    # chain_loose_starts recovery of the prosecution provisions.
    ("ita25-478-evasion", "Section 478 of the Income-tax Act 2025", "evade", False),
    ("ita25-536-repeal-savings", "Section 536 of the Income-tax Act 2025", "hereby repealed", False),

    # ── Currency flags: repealed statutes MUST warn, in-force must NOT ──
    ("ipc-420-flags-repeal", "Section 420 of the Indian Penal Code", "Bharatiya Nyaya Sanhita", True),
    ("crpc-438-flags-repeal", "Section 438 of the CrPC", "Nagarik Suraksha", True),
    ("ita61-4-flags-repeal", "Section 4 of the Income-tax Act 1961", "Income-tax Act, 2025", True),
    ("ni-138-clean", "Section 138 of the Negotiable Instruments Act", "cheque", False),
    ("bns-318-clean", "Section 318 of the Bharatiya Nyaya Sanhita", "cheat", False),
]
