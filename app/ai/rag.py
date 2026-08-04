"""
RAG retrieval pipeline.
Given a user query, retrieves the most relevant law sections
and formats them as grounded citation context for the agent.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

TOP_K = 10         # sections to retrieve (wider reach across the expanded multi-act corpus)
MIN_SCORE = 0.35   # cosine similarity threshold (0–1 scale, lower = more similar in ChromaDB)


def retrieve(query: str, act_filter: Optional[str] = None) -> str:
    """
    Retrieve relevant law sections for the query.
    Returns a formatted string ready to inject into the system prompt.
    Returns empty string if vector store is unavailable.
    """
    try:
        from app.ai.vector_store import get_collection
        collection = get_collection()
    except Exception as e:
        logger.warning(f"Vector store unavailable: {e}")
        return ""

    try:
        where = {"act_id": act_filter} if act_filter else None
        results = collection.query(
            query_texts=[query],
            n_results=min(TOP_K, collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        docs      = results["documents"][0]      if results["documents"]  else []
        metas     = results["metadatas"][0]      if results["metadatas"]  else []
        distances = results["distances"][0]      if results["distances"]  else []

        if not docs:
            return ""

        verified, headings = [], []

        for doc, meta, dist in zip(docs, metas, distances):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            similarity = 1.0 - (dist / 2.0)
            if similarity < MIN_SCORE:
                continue

            act_title  = meta.get("act_title", "Unknown Act")
            act_year   = meta.get("act_year", "")
            act_status = meta.get("act_status", "in_force")
            section    = meta.get("section", "")
            title      = meta.get("title", "")
            note       = meta.get("note", "")
            repealed_by = meta.get("repealed_by", "")

            status_tag = ""
            if act_status == "repealed":
                status_tag = f" [REPEALED — replaced by {repealed_by}; {note}]"

            if meta.get("source_verified") and meta.get("full_text"):
                src = meta.get("source_url", "")
                page = meta.get("page", "")
                verified.append(
                    f"• {act_title} ({act_year}){status_tag} — Section {section}: {title}\n"
                    f"  VERBATIM TEXT (official source): {meta['full_text']}\n"
                    f"  [source: {src}{(' p.' + page) if page else ''}]"
                )
            else:
                headings.append(
                    f"• {act_title} ({act_year}){status_tag} — Section {section}: {title}"
                )

        if not verified and not headings:
            return ""

        parts = []
        if verified:
            parts.append(
                "VERIFIED STATUTORY TEXT (from official source — you MAY quote this "
                "verbatim and MUST cite the section + source):\n" + "\n".join(verified)
            )
        if headings:
            parts.append(
                "SECTION-HEADING MATCHES (heading only — NOT verified full text; you may "
                "name what the section is about but MUST NOT quote operative wording as "
                "verbatim):\n" + "\n".join(headings)
            )
        block = (
            "RETRIEVED LAW SECTIONS — these are the ONLY provisions you may cite as "
            "authority:\n\n" + "\n\n".join(parts)
            + "\n\nIMPORTANT: Cite ONLY sections listed above. For a section listed from a "
            "repealed Act, note it applies only to pre-repeal matters and give the "
            "equivalent section in the new Act where available."
        )
        return block

    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        return ""


# Act aliases → exact act_title as stored in the corpus metadata. Used for the
# deterministic "Section N of <Act>" lookup, which is far more precise than
# semantic search for section-number questions.
_ACT_ALIASES: list[tuple[tuple[str, ...], str]] = [
    (("negotiable instruments", "ni act", "n.i. act", "n i act"), "Negotiable Instruments Act, 1881"),
    (("bharatiya nyaya sanhita", "bns", "nyaya sanhita"), "Bharatiya Nyaya Sanhita, 2023"),
    (("bharatiya nagarik suraksha", "bnss", "nagarik suraksha"), "Bharatiya Nagarik Suraksha Sanhita, 2023"),
    (("bharatiya sakshya", "bsa", "sakshya adhiniyam"), "Bharatiya Sakshya Adhiniyam, 2023"),
    (("indian penal code", "ipc", "penal code"), "Indian Penal Code, 1860"),
    (("code of criminal procedure", "crpc", "cr.p.c", "criminal procedure code"), "Code of Criminal Procedure, 1973"),
    (("code of civil procedure", "cpc", "c.p.c", "civil procedure code"), "Code of Civil Procedure, 1908"),
    (("indian evidence act", "evidence act", "iea"), "Indian Evidence Act, 1872"),
    (("indian contract act", "contract act"), "Indian Contract Act, 1872"),
    (("transfer of property", "tp act", "t.p. act", "tpa"), "Transfer of Property Act, 1882"),
    (("specific relief",), "Specific Relief Act, 1963"),
    (("indian partnership", "partnership act"), "Indian Partnership Act, 1932"),
    (("sale of goods",), "Sale of Goods Act, 1930"),
    (("hindu succession",), "Hindu Succession Act, 1956"),
    (("domestic violence", "dv act", "pwdva"), "Protection of Women from Domestic Violence Act, 2005"),
    (("indian succession",), "Indian Succession Act, 1925"),
    (("pocso", "protection of children from sexual offences"), "Protection of Children from Sexual Offences Act, 2012"),
    (("sarfaesi", "securitisation"), "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act, 2002"),
    (("rera", "real estate regulation", "real estate (regulation"), "Real Estate (Regulation and Development) Act, 2016"),
    (("insolvency and bankruptcy", "ibc", "insolvency code"), "Insolvency and Bankruptcy Code, 2016"),
    (("indian easements", "easements act", "easement"), "Indian Easements Act, 1882"),
    (("limitation act", "limitation"), "Limitation Act, 1963"),
    (("companies act",), "Companies Act, 2013"),
    (("consumer protection",), "Consumer Protection Act, 2019"),
    (("income-tax", "income tax", "it act 1961"), "Income-tax Act, 1961"),
    (("motor vehicles",), "Motor Vehicles Act, 1988"),
    (("information technology act", "it act"), "Information Technology Act, 2000"),
    (("hindu marriage",), "Hindu Marriage Act, 1955"),
    (("right to information", "rti"), "Right to Information Act, 2005"),
    (("arbitration",), "Arbitration and Conciliation Act, 1996"),
    (("goods and services tax", "gst", "cgst"), "Central Goods and Services Tax Act, 2017"),
    # Batch 3 (2026-07-16): litigation staples + new-era laws
    (("narcotic drugs", "ndps", "psychotropic"), "Narcotic Drugs and Psychotropic Substances Act, 1985"),
    (("prevention of corruption", "pc act", "poca"), "Prevention of Corruption Act, 1988"),
    (("money-laundering", "money laundering", "pmla"), "Prevention of Money-laundering Act, 2002"),
    (("digital personal data protection", "dpdp", "data protection act"), "Digital Personal Data Protection Act, 2023"),
    (("commercial courts", "commercial court"), "Commercial Courts Act, 2015"),
    # Batch 4 (2026-07-16)
    (("prevention of atrocities", "sc/st act", "sc st act", "atrocities act"),
     "Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, 1989"),
    (("juvenile justice", "jj act"), "Juvenile Justice (Care and Protection of Children) Act, 2015"),
    (("mediation act",), "Mediation Act, 2023"),
    (("registration act",), "Registration Act, 1908"),
    (("industrial disputes", "id act"), "Industrial Disputes Act, 1947"),
    (("senior citizens", "maintenance and welfare of parents"),
     "Maintenance and Welfare of Parents and Senior Citizens Act, 2007"),
    # Batch 5 (2026-07-16)
    (("family courts", "family court"), "Family Courts Act, 1984"),
    (("legal services authorities", "legal services act", "lok adalat"), "Legal Services Authorities Act, 1987"),
    (("muslim women", "triple talaq", "talaq"), "Muslim Women (Protection of Rights on Marriage) Act, 2019"),
    (("guardians and wards", "guardian and ward"), "Guardians and Wards Act, 1890"),
    (("stamp act", "indian stamp"), "Indian Stamp Act, 1899"),
    (("income-tax rules", "income tax rules", "it rules"), "Income-tax Rules, 2026"),
    # ITA-2025 slice (2026-07-20). Bare "income tax" stays on the REPEALED 1961 Act
    # (IPC→BNS precedent: the currency layer flags the repeal and points to the successor;
    # pre-2026 tax years still litigate under 1961). Any 2025-qualified form wins here
    # via longest-alias-match.
    (("income-tax act 2025", "income tax act 2025", "income-tax act, 2025",
      "income tax act, 2025", "income-tax 2025", "income tax 2025", "ita 2025",
      "it act 2025", "new income tax act"), "Income-tax Act, 2025"),
    (("constitution",), "The Constitution of India"),
]

_SECTION_RE = re.compile(
    # "Section 138", "s.138A", "u/s 420" → capture the number + an attached suffix only
    # (no trailing space-word, so "138 of" yields "138", "138A" yields "138A").
    # "article"/"art." are included because the Constitution's provisions are cited as
    # "Article 21", not "Section 21" — without them the deterministic path never fired for
    # the Constitution. The leading \b stops "art" matching inside words like "start".
    # "rule" included for subordinate legislation (Income-tax Rules, 2026 — cited "Rule 12").
    # Group 1 = the citation KEYWORD (so we know "Article" vs "Section" intent), group 2 = number.
    r"\b(section|sec\.?|s\.?|u/s|under section|articles?|arts?\.?|rules?)\s*([0-9]{1,4}[A-Za-z]{0,2})",
    re.IGNORECASE,
)


def _detect_act(query_lc: str) -> Optional[str]:
    """Return the exact corpus act_title whose alias appears in the query, if any."""
    best = None
    for aliases, title in _ACT_ALIASES:
        for a in aliases:
            if a in query_lc:
                # prefer the longest matching alias (most specific)
                if best is None or len(a) > best[0]:
                    best = (len(a), title)
    return best[1] if best else None


def retrieve_by_section(query: str) -> str:
    """Deterministic lookup: if the query names 'Section N of <Act>', fetch THAT
    section's verbatim text by exact metadata match (no embedding similarity).
    Returns a VERIFIED STATUTORY TEXT block, or '' if nothing matched.

    This is the precise path for section-number questions, which semantic search
    handles poorly. Zero hallucination risk — the exact section text is injected.
    """
    # Capture citation KIND ("article" vs "section"/"rule") with each number so the Limitation
    # Act — which has BOTH numbered body sections (1-32) AND a Schedule of numbered articles
    # (1-137) — is disambiguated by user intent: "Article 5" => Schedule article 5 (accounts),
    # "Section 5" => body section 5 (condonation of delay). For every other act the Sch.* namespace
    # is absent, so the kind has no effect and behaviour is unchanged. (No keyword => no match =>
    # semantic fallback, which is the right behaviour when intent is genuinely absent.)
    ordered: list[tuple[str, str]] = []
    seen_nums: set[str] = set()
    for m in _SECTION_RE.finditer(query):
        kind = "article" if m.group(1).lower().startswith("art") else "section"
        num = m.group(2).replace(" ", "").upper()
        if num in seen_nums:
            continue
        seen_nums.add(num)
        ordered.append((kind, num))
    if not ordered:
        return ""
    act_title = _detect_act(query.lower())
    if not act_title:
        return ""  # need an act to disambiguate (s.138 exists in several acts)
    try:
        from app.ai.vector_store import get_collection
        collection = get_collection()
    except Exception as e:
        logger.warning(f"Vector store unavailable for section lookup: {e}")
        return ""

    entries: list[str] = []
    for kind, sec in ordered:
        meta = None
        # Try the section id in intent order. The Schedule-article namespace ("Article 137 of the
        # Limitation Act" is stored as section "Sch.137") is exact-match on act+section, so acts
        # without Sch.* ids are unaffected either way.
        base = sec.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        if kind == "article":
            # Article intent → Schedule-article FIRST (Limitation Sch.N). For the Constitution,
            # whose articles ARE the body, Sch.N doesn't exist so it falls through to the body.
            candidates = (f"Sch.{sec}", sec, base)
        else:
            # Section/rule intent → body FIRST; Schedule only as a last resort (so "Section 65 of
            # the Limitation Act", which has no body s.65, still resolves to the Schedule article).
            candidates = (sec, base, f"Sch.{sec}")
        for sval in candidates:
            try:
                got = collection.get(
                    where={"$and": [{"act_title": act_title}, {"section": sval}]},
                    include=["metadatas"], limit=1,
                )
            except Exception:
                got = {"metadatas": []}
            if got.get("metadatas"):
                meta = got["metadatas"][0]
                break
        if not meta:
            continue
        title = meta.get("title", "")
        if meta.get("source_verified") and meta.get("full_text"):
            src = meta.get("source_url", ""); page = meta.get("page", "")
            # Currency warning: the model MUST tell the advocate when the provision comes
            # from a repealed statute (IPC/CrPC/Evidence → BNS/BNSS/BSA; ITA 1961 → ITA 2025).
            repeal = ""
            if meta.get("act_status") == "repealed":
                note = meta.get("note", "") or (
                    "This Act stands repealed" +
                    (f" — now see {meta.get('repealed_by')}" if meta.get("repealed_by") else "") + ".")
                repeal = (f"\n  ⚠ REPEALED STATUTE: {note} State this to the user and, where a "
                          f"successor provision exists, point them to it.")
            entries.append(
                f"• {act_title} — Section {meta.get('section')}: {title}\n"
                f"  VERBATIM TEXT (official source): {meta['full_text']}\n"
                f"  [source: {src}{(' p.' + str(page)) if page else ''}]{repeal}"
            )
        elif title:
            entries.append(
                f"• {act_title} — Section {meta.get('section')}: {title} "
                f"[heading only — exact wording unverified; direct user to indiacode.nic.in]"
            )
    if not entries:
        return ""
    return (
        "EXACT SECTION REQUESTED BY THE USER (authoritative — answer from this verbatim "
        "text and cite it):\n"
        "VERIFIED STATUTORY TEXT (from official source — you MAY quote this verbatim and "
        "MUST cite the section + source):\n" + "\n".join(entries)
    )


# Words to ignore when matching query terms against section titles.
_TITLE_STOP = {
    "what", "whats", "is", "are", "the", "a", "an", "of", "for", "under", "and", "or",
    "in", "to", "does", "deal", "deals", "with", "explain", "tell", "me", "about",
    "please", "provision", "provisions", "law", "laws", "india", "indian", "section",
    "sections", "act", "code", "punishment", "punishable", "offence", "offense", "case",
    "give", "show", "define", "definition", "meaning", "how", "when", "who", "whom",
    "this", "that", "from", "into", "upon", "their", "there", "which",
}


def retrieve_by_title_keyword(query: str, limit: int = 3) -> str:
    """When the query names an Act and a topic word that matches a SECTION TITLE
    (e.g. 'cheating' → s.318 'Cheating'), inject those sections' verbatim text.
    High precision for offence-name questions that semantic search ranks poorly.
    Only fires when an Act is named (keeps it scoped). Returns '' if nothing matched.
    """
    act_title = _detect_act(query.lower())
    if not act_title:
        return ""
    toks = [t for t in re.findall(r"[a-z]{4,}", query.lower()) if t not in _TITLE_STOP]
    if not toks:
        return ""
    try:
        from app.ai.vector_store import get_collection
        collection = get_collection()
        got = collection.get(where={"act_title": act_title}, include=["metadatas"])
    except Exception as e:
        logger.warning(f"Title-keyword lookup unavailable: {e}")
        return ""
    scored: list[tuple] = []
    for m in got.get("metadatas", []):
        title = (m.get("title") or "").lower()
        if not title:
            continue
        score = sum(1 for t in toks if t in title)
        if not score:
            continue
        # Prefer the most CENTRAL section: an exact one-word title match (e.g. title
        # "cheating" for the topic "cheating") and shorter titles outrank qualified
        # variants ("cheating by personation"). Sort: more matches, exact, shorter title.
        exact = 1 if title.strip() in toks else 0
        scored.append((-score, -exact, len(title), m))
    if not scored:
        return ""
    scored.sort(key=lambda x: x[:3])
    # If an EXACT single-word title match exists (e.g. title "Cheating" for topic
    # "cheating"), that is the base offence — inject ONLY exact matches so a small
    # model can't latch onto a qualified variant (e.g. "Cheating by personation").
    exacts = [t for t in scored if t[1] == -1]
    chosen = (exacts if exacts else scored)[:limit]
    entries = []
    for *_rank, m in chosen:
        sec = m.get("section")
        title = m.get("title", "")
        if m.get("source_verified") and m.get("full_text"):
            src = m.get("source_url", "")
            entries.append(
                f"• {act_title} — Section {sec}: {title}\n"
                f"  VERBATIM TEXT (official source): {m['full_text']}\n"
                f"  [source: {src}]"
            )
        elif title:
            entries.append(f"• {act_title} — Section {sec}: {title} [heading only]")
    if not entries:
        return ""
    return (
        "SECTIONS MATCHING THE TOPIC NAMED BY THE USER (authoritative — answer from this "
        "verbatim text and cite it):\n"
        "VERIFIED STATUTORY TEXT (from official source — you MAY quote this verbatim and "
        "MUST cite the section + source):\n" + "\n".join(entries)
    )


def _provision_unit(act_title: str) -> tuple[str, str]:
    """(full, abbrev) nomenclature for an Act's provisions. The Constitution's provisions
    are ARTICLES, not sections — citing 'Article 21' as 's.21' is wrong nomenclature and
    reads as an error to any advocate. Everything else uses 'Section'."""
    if "constitution" in (act_title or "").lower():
        return "Article", "Art."
    return "Section", "s."


def format_citation(act: str, year: str, section: str, title: str,
                    url: str = "", page: str = "", verified: bool = True,
                    status: str = "in_force", repealed_by: str = "") -> str:
    """A copy-ready citation an advocate can paste, built ONLY from stored provenance
    (no invented para/amendment data). E.g.:
      'Article 21, Constitution of India — Protection of life and personal liberty
       (India Code, indiacode.nic.in, p.30)'
      's.138, Negotiable Instruments Act, 1881 — Dishonour of cheque … (India Code …, p.…)'
    Unverified (heading-only) provisions say so, so nothing is over-claimed."""
    act_str = act.replace("The ", "").strip()   # 'Constitution of India', not 'The Constitution…'
    # Seventh-Schedule entries carry a self-describing title ("Seventh Schedule, Union List,
    # Entry N — …"), so cite the title directly rather than an "Art.Sch7.…" pseudo-number.
    if str(section).startswith("Sch"):
        base = title or str(section)
        if verified:
            return f"{base}, {act_str} (India Code, indiacode.nic.in{', p.'+page if page else ''})"
        return f"{base}, {act_str} (heading only — verify exact text at indiacode.nic.in)"
    _full, abbr = _provision_unit(act)
    head = f"{abbr}{section}, {act_str}"
    # Many corpus act titles already carry the year ('… Act, 1881'); only append it when
    # absent. The Constitution is conventionally cited without a year.
    if year and year not in act_str and "constitution" not in act_str.lower():
        head += f", {year}"
    if title:
        head += f" — {title}"
    if verified:
        pin = ", p." + page if page else ""
        head += f" (India Code, indiacode.nic.in{pin})"
    else:
        head += " (heading only — verify exact text at indiacode.nic.in)"
    # Currency flag (P2 roadmap): a repealed provision is NEVER cited as if in force.
    if status == "repealed":
        head += (f" [REPEALED — now see {repealed_by}]" if repealed_by else " [REPEALED]")
    return head


def retrieve_structured(query: str, top_k: int = 6) -> list[dict]:
    """Structured top sections for the query (for a 'Sources' summary in the chat).
    Returns [{act, year, section, unit, abbr, page, title, url, verified, citation}],
    verified-verbatim first. [] on failure."""
    try:
        from app.ai.vector_store import get_collection
        collection = get_collection()
        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, collection.count()),
            include=["metadatas", "distances"],
        )
        metas = results["metadatas"][0] if results["metadatas"] else []
        dists = results["distances"][0] if results["distances"] else []
        out = []
        for meta, dist in zip(metas, dists):
            if (1.0 - dist / 2.0) < MIN_SCORE:
                continue
            act = meta.get("act_title", ""); year = str(meta.get("act_year", ""))
            section = str(meta.get("section", "")); title = meta.get("title", "")
            url = meta.get("source_url", ""); page = str(meta.get("page", "") or "")
            verified = bool(meta.get("source_verified"))
            status = meta.get("act_status", "in_force")
            repealed_by = meta.get("repealed_by", "")
            unit, abbr = _provision_unit(act)
            out.append({
                "act": act, "year": year, "section": section, "title": title,
                "url": url, "page": page, "verified": verified,
                "unit": unit, "abbr": abbr,
                "status": status, "repealed_by": repealed_by,
                "citation": format_citation(act, year, section, title, url, page, verified,
                                            status=status, repealed_by=repealed_by),
            })
        # verified-verbatim first, keep order otherwise
        out.sort(key=lambda s: 0 if s["verified"] else 1)
        return out
    except Exception as e:
        logger.warning(f"Structured retrieval failed: {e}")
        return []


def retrieve_act_summary(act_id: str) -> str:
    """Return all indexed sections for a specific Act (for full-act questions)."""
    try:
        from app.ai.vector_store import get_collection
        collection = get_collection()
        results = collection.get(
            where={"act_id": act_id},
            include=["documents", "metadatas"],
        )
        metas = results.get("metadatas", [])
        if not metas:
            return ""

        lines = []
        for m in metas:
            lines.append(f"  s.{m['section']}: {m['title']}")

        act_title = metas[0].get("act_title", act_id) if metas else act_id
        return f"FULL SECTION INDEX — {act_title}:\n" + "\n".join(lines)

    except Exception as e:
        logger.warning(f"Act summary retrieval failed: {e}")
        return ""
