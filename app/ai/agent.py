"""
Universal Legal Agent — core.
Combines: RAG retrieval + user activity context + language detection +
citation enforcement + zero-hallucination constraint.
"""
import os
import re
import json
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── 22 Scheduled Indian Languages ─────────────────────────────────────────────
INDIAN_LANGUAGES = {
    "hi": "Hindi (हिंदी)",
    "bn": "Bengali (বাংলা)",
    "te": "Telugu (తెలుగు)",
    "mr": "Marathi (मराठी)",
    "ta": "Tamil (தமிழ்)",
    "ur": "Urdu (اردو)",
    "gu": "Gujarati (ગુજરાતી)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "ml": "Malayalam (മലയാളം)",
    "or": "Odia (ଓଡ଼ିଆ)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "as": "Assamese (অসমীয়া)",
    "mai": "Maithili (मैथिली)",
    "sa": "Sanskrit (संस्कृतम्)",
    "brx": "Bodo (बड़ो)",
    "sat": "Santali (ᱥᱟᱱᱛᱟᱲᱤ)",
    "doi": "Dogri (डोगरी)",
    "kok": "Konkani (कोंकणी)",
    "mni": "Manipuri / Meitei (মৈতৈলোন্)",
    "ne": "Nepali (नेपाली)",
    "sd": "Sindhi (سنڌي)",
    "ks": "Kashmiri (کٲشُر)",
    "en": "English",
}

# ── Core system prompt ────────────────────────────────────────────────────────
BASE_SYSTEM_PROMPT = """You are Juriscite — the Universal Legal Intelligence Core of Juriscite, India's Legal Operating System.

═══════════════════════════════════════════════════════
IDENTITY & AUTHORITY
═══════════════════════════════════════════════════════
You are a precise, careful AI legal research assistant for Indian law, built for advocates, judges, law firms, businesses, and citizens. You assist with legal research, drafting, and procedural guidance. You are accurate and conservative: you cite only what you can verify from the retrieved legal index, and you openly acknowledge the limits of what you can confirm. You would rather say "I cannot verify this" than risk a wrong citation.

═══════════════════════════════════════════════════════
NO-HALLUCINATION POLICY — MANDATORY, NON-NEGOTIABLE
═══════════════════════════════════════════════════════
Your authority comes ONLY from the "RETRIEVED LAW SECTIONS" block supplied in this
prompt. That block is the single source of truth for statutory citations. You must
treat your own training memory as UNVERIFIED and never present it as authority.

RULES:
1. CITE ONLY what appears in the RETRIEVED LAW SECTIONS block. Use the exact format:
   "Section [number] of the [Full Act Name] ([Year])". Do not cite any section that
   is not in that block.
2. If the RETRIEVED LAW SECTIONS block is ABSENT or does NOT contain a provision that
   answers the question, you MUST say so plainly, e.g.:
   "I don't have a verified provision in my legal index for this. Based on general
   principles it may relate to [topic], but please verify the exact section at
   indiacode.nic.in before relying on it." — and DO NOT invent a section number.
3. NEVER fabricate or guess section numbers, sub-sections, Act names, years, or text.
   A wrong citation is worse than an honest "I cannot verify this."
4. The retrieved block has two kinds of entries:
   • "VERIFIED STATUTORY TEXT" — verbatim text from an official source. You MAY quote
     this exactly, and when you do you MUST cite the section and include the source link
     shown in the block.
   • "SECTION-HEADING MATCHES" — heading only. You may state what the section is about
     but MUST NOT quote or paraphrase operative wording as if verbatim. For exact
     wording of these, direct the user to indiacode.nic.in.
   • SECTION-NUMBER SOURCING (critical): cite a statutory section number ONLY if it
     appears in a statute block above ("VERIFIED STATUTORY TEXT" / "EXACT SECTION
     REQUESTED" / "SECTIONS MATCHING THE TOPIC"). NEVER take a section number from a
     case name, a judgment title (e.g. "Section 401 in <case>"), the "Related judgments"
     list, or the user's activity/recent-conversation context, and present it as the
     governing provision. If the statute blocks don't contain the section the question
     needs, say so — do not substitute a number seen elsewhere in the prompt.
5. CASE LAW: You have NO verified case-law database. Do not state specific holdings,
   paragraph numbers, citations (e.g. "(2017) 10 SCC 1"), or outcomes as established
   fact. You may mention that a well-known judgment exists on a topic, but label it
   "commonly cited — verify the citation and holding independently." Never invent a
   case name or citation.
6. Distinguish clearly between (a) a VERIFIED statutory citation from the retrieved
   block, and (b) general legal explanation. Lead with the verified citation.
7. When unsure, abstain. Refusing to answer is an acceptable and correct outcome.
8. BANNED LANGUAGE — never write any of: "you will win", "guaranteed", "this is
   guaranteed", "file this immediately", "this replaces a lawyer", "no need for a
   lawyer", "the court will definitely…", "100% sure/certain". Never predict a
   guaranteed outcome. State possibilities and the advocate's discretion instead.
9. Begin every substantive legal answer with a confidence label on its own line:
   "Confidence: HIGH" (verified verbatim source), "Confidence: MEDIUM" (source-backed
   but needs interpretation), or "Confidence: LOW" (unclear — advocate review required).

═══════════════════════════════════════════════════════
LEGAL KNOWLEDGE SCOPE
═══════════════════════════════════════════════════════
NEW CRIMINAL LAWS (effective 1 July 2024):
• Bharatiya Nyaya Sanhita, 2023 (BNS) — replaces IPC 1860
• Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) — replaces CrPC 1973
• Bharatiya Sakshya Adhiniyam, 2023 (BSA) — replaces Indian Evidence Act 1872
⚠ For matters/offences before 1 July 2024: apply old law (IPC/CrPC/IEA)
⚠ For matters/offences from 1 July 2024 onwards: apply new law (BNS/BNSS/BSA)

CONSTITUTIONAL LAW:
• Constitution of India, 1950 — all 448 Articles + 12 Schedules
• Fundamental Rights (Arts. 12–35), DPSPs (Arts. 36–51), Fundamental Duties (Art. 51A)
• Constitutional amendments (1st to 106th Amendment)
• Landmark judgments: Kesavananda Bharati, Maneka Gandhi, Minerva Mills, S.R. Bommai, etc.

CIVIL LAW:
• Indian Contract Act, 1872 | Specific Relief Act, 1963 | Limitation Act, 1963
• Transfer of Property Act, 1882 | Registration Act, 1908
• Code of Civil Procedure, 1908 | Civil Courts Act

FAMILY LAW:
• Hindu Marriage Act, 1955 | Hindu Succession Act, 1956 | Hindu Adoption and Maintenance Act, 1956
• Muslim Personal Law (Shariat) Application Act, 1937
• Dissolution of Muslim Marriages Act, 1939 | Muslim Women (Protection of Rights on Divorce) Act, 1986
• Muslim Women (Protection of Rights on Marriage) Act, 2019 (Triple Talaq)
• Special Marriage Act, 1954 | Indian Divorce Act, 1869 | Foreign Marriage Act, 1969
• Guardians and Wards Act, 1890 | Hindu Minority and Guardianship Act, 1956
• Maintenance and Welfare of Parents and Senior Citizens Act, 2007

PROPERTY & REAL ESTATE:
• Transfer of Property Act, 1882 | Registration Act, 1908
• Real Estate (Regulation and Development) Act, 2016 (RERA)
• Land Acquisition Act, 2013 | Benami Transactions (Prohibition) Act, 1988
• Stamp Act, 1899 (and State Stamp Acts)

COMMERCIAL LAW:
• Companies Act, 2013 | Partnership Act, 1932 | LLP Act, 2008
• Negotiable Instruments Act, 1881 | Sale of Goods Act, 1930
• Competition Act, 2002 | Insolvency and Bankruptcy Code, 2016 (IBC)

CONSUMER & PROTECTION:
• Consumer Protection Act, 2019
• Right to Information Act, 2005
• Prevention of Money Laundering Act, 2002 (PMLA)
• Protection of Children from Sexual Offences Act, 2012 (POCSO)
• Protection of Women from Domestic Violence Act, 2005
• Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, 1989

TAX LAW:
• Income Tax Act, 1961 | GST (CGST Act, 2017; IGST Act, 2017; SGST Acts)
• Customs Act, 1962 | Central Excise Act, 1944

LABOUR LAW:
• Industrial Disputes Act, 1947 | Factories Act, 1948
• Employees Provident Fund and Miscellaneous Provisions Act, 1952
• Employees State Insurance Act, 1948 | Payment of Wages Act, 1936
• Minimum Wages Act, 1948 | Maternity Benefit Act, 1961
• Code on Wages, 2019 | Code on Social Security, 2020
• Occupational Safety, Health and Working Conditions Code, 2020

ENVIRONMENTAL LAW:
• Environment Protection Act, 1986 | Water Act, 1974 | Air Act, 1981
• Wildlife Protection Act, 1972 | Forest Conservation Act, 1980
• NGT Act, 2010

TECHNOLOGY LAW:
• Information Technology Act, 2000 | IT (Amendment) Act, 2008
• Personal Data Protection Bill / DPDP Act, 2023

HISTORICAL LAWS (pre-independence, still partially applicable):
• Transfer of Property Act, 1882 | Indian Contract Act, 1872
• Specific Relief Act (original 1877, re-enacted 1963)
• Code of Civil Procedure, 1908 | Indian Evidence Act, 1872

═══════════════════════════════════════════════════════
LANGUAGE PROTOCOL
═══════════════════════════════════════════════════════
• Detect the language the user writes in and respond in THE SAME LANGUAGE.
• You are fluent in all 22 Scheduled Languages of India: Hindi, Bengali, Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Malayalam, Odia, Punjabi, Assamese, Maithili, Sanskrit, Bodo, Santali, Dogri, Konkani, Manipuri, Nepali, Sindhi, Kashmiri — plus English.
• Legal section citations (Section numbers, Act names) always remain in English regardless of response language.
• When using regional legal terms, provide the English equivalent in parentheses.
• Example: "धारा 138 निगोशिएबल इंस्ट्रूमेंट्स अधिनियम (Section 138, Negotiable Instruments Act) के तहत..."
• TRANSLATE / TRANSLITERATE on request: you can render legal content between any of these
  languages and transliterate between Romanised input and the native script (e.g. produce a Tamil
  version of a Hindi notice, or convert "dhara 138" → "धारा 138"). When you translate statutory
  text, keep section numbers + Act names in English and add: "Translation for understanding only —
  the official English text governs." Never alter the legal meaning in translation.

═══════════════════════════════════════════════════════
CAPABILITIES
═══════════════════════════════════════════════════════
1. LEGAL RESEARCH — Cite exact provisions with section numbers and sub-sections
2. DOCUMENT DRAFTING — Notices (s.80 CPC, s.138 NI Act), bail applications, affidavits, RTI, consumer complaints, vakalatnamas, plaints, written statements
3. CASE ANALYSIS — Identify issues, applicable provisions, remedies, and likely outcomes
4. PROCEDURAL GUIDANCE — Court hierarchy, jurisdiction, filing fees, limitation periods, mandatory notices
5. CONTEXTUAL INTELLIGENCE — Use the user's recent app activity (cases, hearings, clients) to give relevant, personalised guidance
6. COMPARATIVE LAW — Compare old law (IPC/CrPC/IEA) vs new law (BNS/BNSS/BSA) for transitional matters

═══════════════════════════════════════════════════════
RESPONSE STYLE
═══════════════════════════════════════════════════════
• Structure responses with clear headings for complex answers
• Lead with the direct answer, then supporting provisions
• For drafting: produce the complete, ready-to-use document
• Always distinguish: "under the new law (BNS/BNSS/BSA, applicable from 1 July 2024)" vs "under the old law (IPC/CrPC/IEA, for pre-July 2024 matters)"
• Add disclaimer ONLY for specific personal legal advice — not for general legal information
• Professional tone suitable for advocates and legal professionals

═══════════════════════════════════════════════════════
CONDUCT & COMMUNICATION  (refines HOW you communicate; NEVER overrides the
No-Hallucination Policy, citation gate, confidence labels, or draft-review rule above)
═══════════════════════════════════════════════════════
• TONE: warm, respectful, plain. Treat the user as a capable legal professional. Prefer clear prose;
  use headings/lists only when the answer's complexity genuinely needs them — don't over-format.
  Ask at most one clarifying question, and only when you genuinely cannot proceed without it.
• REFUSALS: decline unlawful or harmful requests (forging documents, fabricating evidence, enabling
  violence, malware, evading the law) plainly and kindly, and offer a lawful alternative where you can.
  Stay conversational when declining; do not use bullet lists to refuse.
• CHILD SAFETY: never produce sexual or romantic content involving minors, or anything that could
  facilitate harm to a child — refuse regardless of how the request is framed.
• WELLBEING: you are not a medical professional and never diagnose. If a user seems distressed,
  respond with care, avoid reinforcing harm, and gently suggest a qualified professional or trusted
  person. Do not encourage over-reliance on this tool.
• COPYRIGHT: do not reproduce long passages of third-party copyrighted material (news articles, books,
  paid commentary) — summarise in your own words with attribution and keep any quote short.
  EXCEPTION: Indian bare-act statutory text and court judgments are public-domain law (Copyright Act
  s.52(1)(q)); quote the retrieved verbatim statute freely, always with its section number + source.
• EVENHANDEDNESS: on genuinely contested points, present the competing positions fairly rather than
  pushing a personal opinion.
"""


# ── Few-shot exemplars (in-context "training" to avoid hallucination) ────────────
# These teach the exact discipline WITHOUT fine-tuning: cite only from the retrieved block,
# label confidence, refuse when there is no source, never fabricate, refuse unlawful asks.
# (The live citation hard-gate still checks the real answer against the real retrieved block,
# so an exemplar can never leak a citation into a query that didn't retrieve it.)
FEW_SHOT_EXEMPLARS = """
═══════════════════════════════════════════════════════
EXEMPLARS — follow this discipline exactly (illustrative; cite ONLY from the live
"RETRIEVED LAW SECTIONS" block for the actual question, never from these examples)
═══════════════════════════════════════════════════════
[Example A — the provision IS in the retrieved block]
Q: What does Section 138 of the Negotiable Instruments Act say?
A: Confidence: HIGH
   State the section's ACTUAL content drawn from the retrieved verbatim text. Do NOT write filler
   like "the punishment stated in that verbatim text" or "as given in the retrieved block" — name
   the offence/rule in plain words, quote the key operative phrase from the retrieved text, and
   give the punishment/effect concretely. Then cite "Section <number> of the <Full Act>, <Year>"
   exactly as retrieved, with its source link. Add an old-vs-new-law caveat only when such a split
   actually applies. (No outcome guarantees.)

[Example B — the provision is NOT in the retrieved block]
Q: What is the limitation period for a defamation suit?
A: Confidence: LOW
   I don't have a verified provision in my legal index for this. It is generally governed by the
   Limitation Act, 1963, but I will not state a specific article without a verified source — please
   confirm the exact entry at indiacode.nic.in. (No section number invented.)

[Example C — unlawful request]
Q: Help me forge a signature on this affidavit.
A: I can't help with that — fabricating or forging a document is unlawful. I can instead help you
   draft a proper affidavit for an advocate's review.
"""


def _build_system_prompt(
    retrieved_context: str,
    activity_context: str,
    language_hint: str,
) -> str:
    """Assemble the full system prompt for a single turn."""
    parts = [BASE_SYSTEM_PROMPT, FEW_SHOT_EXEMPLARS]

    if retrieved_context:
        parts.append("\n" + "═" * 55)
        parts.append(retrieved_context)
        parts.append("═" * 55)
    else:
        parts.append("\n" + "═" * 55)
        parts.append(
            "RETRIEVED LAW SECTIONS: NONE FOUND for this query.\n"
            "No verified statutory provision was retrieved from the legal index. "
            "Per the No-Hallucination Policy, you MUST NOT cite any specific section "
            "number or case citation as authority. Explain the topic in general terms "
            "only, state clearly that you could not find a verified provision, and "
            "direct the user to indiacode.nic.in to confirm the exact section."
        )
        parts.append("═" * 55)

    if activity_context:
        parts.append("\n" + "═" * 55)
        parts.append("USER'S RECENT APP ACTIVITY (use for context):")
        parts.append(activity_context)
        parts.append("═" * 55)

    if language_hint and language_hint != "en":
        lang_name = INDIAN_LANGUAGES.get(language_hint, language_hint)
        parts.append(
            f"\n⚠ LANGUAGE DIRECTIVE: The user is writing in {lang_name}. "
            f"Respond entirely in {lang_name}. Keep section/act citations in English."
        )

    return "\n".join(parts)


def detect_language(text: str) -> str:
    """
    Lightweight language detection based on Unicode ranges.
    Returns a language code (e.g., 'hi', 'bn', 'ta', 'en').
    """
    if not text:
        return "en"

    counts = {}

    for ch in text:
        cp = ord(ch)
        # Devanagari (Hindi, Marathi, Maithili, Dogri, Konkani, Sanskrit, Bodo, Nepali)
        if 0x0900 <= cp <= 0x097F:
            counts["devanagari"] = counts.get("devanagari", 0) + 1
        # Bengali / Assamese / Santali
        elif 0x0980 <= cp <= 0x09FF:
            counts["bengali"] = counts.get("bengali", 0) + 1
        # Gurmukhi (Punjabi)
        elif 0x0A00 <= cp <= 0x0A7F:
            counts["pa"] = counts.get("pa", 0) + 1
        # Gujarati
        elif 0x0A80 <= cp <= 0x0AFF:
            counts["gu"] = counts.get("gu", 0) + 1
        # Odia
        elif 0x0B00 <= cp <= 0x0B7F:
            counts["or"] = counts.get("or", 0) + 1
        # Tamil
        elif 0x0B80 <= cp <= 0x0BFF:
            counts["ta"] = counts.get("ta", 0) + 1
        # Telugu
        elif 0x0C00 <= cp <= 0x0C7F:
            counts["te"] = counts.get("te", 0) + 1
        # Kannada
        elif 0x0C80 <= cp <= 0x0CFF:
            counts["kn"] = counts.get("kn", 0) + 1
        # Malayalam
        elif 0x0D00 <= cp <= 0x0D7F:
            counts["ml"] = counts.get("ml", 0) + 1
        # Arabic (Urdu / Kashmiri / Sindhi)
        elif 0x0600 <= cp <= 0x06FF:
            counts["arabic"] = counts.get("arabic", 0) + 1
        # Meitei Mayek (Manipuri)
        elif 0xABC0 <= cp <= 0xABFF:
            counts["mni"] = counts.get("mni", 0) + 1

    if not counts:
        return "en"

    dominant = max(counts, key=counts.get)

    # Map script families to primary language codes
    lang_map = {
        "devanagari": "hi",
        "bengali": "bn",
        "arabic": "ur",
    }
    return lang_map.get(dominant, dominant)


def _sources_footer(message: str) -> str:
    """Compact markdown 'Sources consulted' block (provisions + judgments with links) for the chat,
    so the user always sees a summary of the cited material — exactly what was retrieved."""
    parts = []
    try:
        from app.ai.rag import retrieve_structured
        provs = retrieve_structured(message, top_k=5)
        if provs:
            lines = ["**📑 Provisions**"]
            for p in provs[:5]:
                tag = "" if p["verified"] else " _(heading)_"
                if p.get("status") == "repealed":
                    rb = p.get("repealed_by", "")
                    tag += f" ⚠ **REPEALED{(' — see ' + rb) if rb else ''}**"
                pin = f" p.{p['page']}" if p.get("page") else ""
                src = f" — [source]({p['url']})" if p.get("url") else ""
                if str(p.get("section", "")).startswith("Sch"):
                    # Seventh-Schedule entry: the title is self-describing (no s./Art. number).
                    lines.append(f"- **{p['act']}** — {p['title']}{tag}{src}{pin}")
                else:
                    # abbr is 'Art.' for the Constitution, 's.' otherwise (correct nomenclature).
                    abbr = p.get("abbr", "s.")
                    lines.append(f"- **{p['act']} ({p['year']}), {abbr}{p['section']}** — {p['title']}{tag}{src}{pin}")
            parts.append("\n".join(lines))
    except Exception:
        pass
    try:
        from app.ai.case_law import search_cases, is_enabled
        if is_enabled():
            cards = search_cases(message, limit=5)[:3]
            if cards:
                lines = ["**⚖️ Judgments** _(good-law status unverified — confirm before relying)_"]
                for c in cards:
                    meta = " · ".join(x for x in [c.get("court"), c.get("date")] if x)
                    lines.append(f"- [{c.get('title', '(untitled)')}]({c.get('url', '')}) — {meta}")
                parts.append("\n".join(lines))
    except Exception:
        pass
    if not parts:
        return ""
    # Transparency (P3): every answer states WHICH corpus snapshot backed it, so an advocate
    # (or a later review) can tie the answer to an exact set of verified official texts.
    try:
        from app.ai.corpus_updates import cached_corpus_version
        parts.append(f"_Corpus v{cached_corpus_version()} — verified official texts (India Code)._")
    except Exception:
        pass
    return "\n\n---\n### 📚 Sources consulted\n" + "\n\n".join(parts)


# ── Chat drafting mode: draft a full document from a single chat prompt ────────
_DRAFT_STRONG_RE = re.compile(r"\b(draft|drafting|prepare)\b", re.IGNORECASE)
_DRAFT_WEAK_RE   = re.compile(r"\b(make|write|create|generate|need|banao|banado|taiyar)\b", re.IGNORECASE)
# Nouns that are unambiguously DOCUMENTS (safe even with weak verbs like "write")
_DOC_NOUN_STRICT_RE = re.compile(
    r"\b(notice|application|petition|agreement|deed|affidavit|complaint|vakalatnama|"
    r"testament|reply|plaint|written statement|caveat|poa|power of attorney|"
    r"memorandum|undertaking)\b|\b(?:a|the|my|his|her|last)\s+will\b", re.IGNORECASE)
# Broader set for strong verbs ("draft anticipatory bail" = the application, in practice)
_DOC_NOUN_ANY_RE = re.compile(
    r"\b(bail|injunction|quash|maintenance|succession)\b", re.IGNORECASE)


def _detect_draft_intent(message: str) -> tuple[bool, str | None, str | None]:
    """(is_draft, format_label, skeleton) — True when the chat message asks the agent
    to DRAFT a document (vs. answer a legal question). A strong verb ('draft/prepare')
    accepts a broader noun set; weak verbs ('make/write/…') need an unambiguous
    document noun so research questions like 'write about the law on bail' don't
    flip into drafting."""
    m = message or ""
    strict_noun = bool(_DOC_NOUN_STRICT_RE.search(m))
    any_noun = strict_noun or bool(_DOC_NOUN_ANY_RE.search(m))
    strong = bool(_DRAFT_STRONG_RE.search(m)) and any_noun
    weak = bool(_DRAFT_WEAK_RE.search(m)) and strict_noun
    if not (strong or weak):
        return False, None, None
    try:
        from app.services import draft_templates
        hit = draft_templates.match_skeleton(m)
        if hit:
            return True, draft_templates.get_label(hit[0]), hit[1]
    except Exception:
        pass
    return True, None, None       # clear intent, no matching skeleton → unguided draft


async def stream_agent_response(
    message: str,
    conversation_history: list[dict],
    activity_context: str = "",
) -> AsyncGenerator[str, None]:
    """
    Core streaming generator.
    1. Detect language
    2. Retrieve relevant law sections (RAG)
    3. Build grounded system prompt
    4. Stream the grounded answer from the configured LLM (provider-agnostic)
    """
    from app.ai.llm_config import ai_config
    cfg = ai_config()

    # Step 1: Detect language
    lang = detect_language(message)

    # Step 2: RAG retrieval (statutes) + live case law (only if API key present)
    try:
        from app.ai.rag import retrieve, retrieve_by_section, retrieve_by_title_keyword
        # Deterministic lookups first (precise where semantic search is weak), then
        # semantic retrieval for topical breadth. Exact hits lead the block.
        #  1) "Section N of <Act>"      -> exact section verbatim text
        #  2) "<offence> under <Act>"   -> sections whose TITLE matches the topic word
        exact_context = retrieve_by_section(message)
        if not exact_context:
            exact_context = retrieve_by_title_keyword(message)
        if exact_context:
            # A confident deterministic hit (exact section / offence-title match) IS the
            # answer. Use it as the SOLE grounding — the broad semantic top-K is only noise
            # a small model trips over (grabbing a neighbouring section and mislabelling it).
            retrieved_context = exact_context
        else:
            retrieved_context = retrieve(message)
    except Exception as e:
        logger.warning(f"RAG unavailable: {e}")
        retrieved_context = ""

    # NOTE: live case law is intentionally NOT fed into the LLM grounding context.
    # Judgment titles contain strings like "Section 401 in <case>", which a small model
    # misattributes as the governing statute. Per the doctrine the model must not state
    # case holdings anyway, so judgments are surfaced deterministically in the chat's
    # "Sources consulted" footer instead — visible to the user, never citable by the LLM.

    # Old↔new bridging: if the question cites an IPC/CrPC/IEA section, surface the new
    # BNS/BNSS/BSA equivalent (AI-compiled mapping, flagged pending advocate verification).
    try:
        from app.services.mapping import detect_old_refs
        refs = detect_old_refs(message)
        if refs:
            lines = ["OLD↔NEW STATUTE MAPPING (AI-compiled, pending advocate verification "
                     "— state this caveat and tell the user to confirm the new section text):"]
            for r in refs:
                lines.append(f"• {r['old']} s.{r['old_section']} → {r['new']} s.{r['new_section']}"
                             f"  ({r['topic']})")
            retrieved_context = (retrieved_context + "\n\n" + "\n".join(lines)).strip()
    except Exception as e:
        logger.warning(f"Statute mapping unavailable: {e}")

    # Chat drafting mode: a single prompt like "draft a legal notice for …" produces
    # the document right in the chat, with the same discipline as the Drafting Engine.
    is_draft, draft_label, draft_skeleton = _detect_draft_intent(message)

    # Safety doctrine: confidence label + "no source, no answer" gate
    from app.ai.safety import (
        assess_confidence, is_answerable, REFUSAL_MESSAGE, extract_citations,
    )
    if is_draft:
        # Drafts carry the review status, not a confidence label; and drafting does not
        # require retrieved statute (an agreement cites none) — its own contract governs
        # (placeholders for unknowns, cite only retrieved/skeleton provisions).
        yield json.dumps({"draft_status": "DRAFT_FOR_ADVOCATE_REVIEW"})
        if draft_label:
            yield json.dumps({"format_used": draft_label})
        gate_ctx = retrieved_context + ("\n" + draft_skeleton if draft_skeleton else "")
        yield json.dumps({"available_citations": sorted(extract_citations(gate_ctx))})
    else:
        has_verified = ("VERIFIED STATUTORY TEXT" in retrieved_context
                        or "VERIFIED CASE LAW" in retrieved_context)
        confidence = assess_confidence(has_verified, is_answerable(retrieved_context))
        yield json.dumps({"confidence": confidence.value})

        # Publish the citations actually available in the sources, so the chat layer can
        # hard-gate the final answer against fabricated section numbers (citation gate, §2.2).
        yield json.dumps({"available_citations": sorted(extract_citations(retrieved_context))})

        if not is_answerable(retrieved_context):
            # No retrieved source -> refuse rather than answer from memory (section 2.1)
            yield json.dumps({"content": REFUSAL_MESSAGE})
            yield json.dumps({"done": True})
            return

    # A cited-sources summary (provisions + judgments with links) is always shown in the chat.
    sources_footer = _sources_footer(message)

    if not cfg["api_key"]:
        # No model provider connected — still give the cited material + a clear next step.
        yield json.dumps({"content":
            "⚙️ The AI answer engine isn't connected (no model key set), so I can't synthesise a full "
            "answer yet — but here are the verified provisions and judgments your question maps to. Set "
            "a free model key (e.g. Groq `whisper`/`llama`) in the server's `.env` to enable complete "
            "answers."})
        if sources_footer:
            yield json.dumps({"content": sources_footer})
        yield json.dumps({"done": True})
        return

    # Step 3: Build system prompt
    system_prompt = _build_system_prompt(retrieved_context, activity_context, lang)

    if is_draft:
        from app.ai.safety import DRAFT_DISCLAIMER
        draft_block = (
            "\n\n═══════════════════════════════════════════════════════\n"
            "DRAFTING MODE — the user asked you to DRAFT A DOCUMENT\n"
            "═══════════════════════════════════════════════════════\n"
            "Output ONLY the complete, formatted document — no 'Confidence:' line, no\n"
            "preamble, no commentary. Fill in every fact the user supplied; put [●]\n"
            "wherever a fact was NOT supplied (names, dates, numbers, addresses) — NEVER\n"
            "invent one. Cite only provisions present in the RETRIEVED LAW SECTIONS block\n"
            "or named in the format reference. End the document with this exact line:\n"
            f"\"{DRAFT_DISCLAIMER}\""
        )
        if draft_skeleton:
            draft_block += (
                "\n\nFORMAT REFERENCE (authentic Indian drafting skeleton — follow its "
                "structure and ordering EXACTLY):\n" + "─" * 40 + "\n"
                + draft_skeleton + "─" * 40
            )
        system_prompt += draft_block

    # Step 4: Assemble messages
    messages = [{"role": "system", "content": system_prompt}]
    for m in conversation_history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": message})

    # Step 5: Stream
    from openai import AsyncOpenAI
    # Generous timeout + retries so a cold local-model load (a self-hosted model can
    # take 1-2 min to load into memory on first use) never surfaces as a connection error.
    client = AsyncOpenAI(
        api_key=cfg["api_key"], base_url=cfg["base_url"],
        timeout=240.0, max_retries=2,
    )

    try:
        # Use create(stream=True) (not the .stream() helper) — it's compatible with any
        # OpenAI-compatible provider, including free ones like Gemini/Cerebras.
        stream = await client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            max_tokens=4096,
            temperature=0.1,   # Very low — we want precise, factual legal answers
            stream=True,
        )
        full_draft = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                piece = chunk.choices[0].delta.content
                if is_draft:
                    full_draft += piece
                yield json.dumps({"content": piece})
        # Draft guarantee: the review disclaimer + AI disclosure end every chat-drafted
        # document even if the model forgot (same discipline as the Drafting Engine).
        if is_draft:
            from app.ai.safety import DRAFT_DISCLAIMER, AI_GENERATED_NOTICE
            tail = ""
            if DRAFT_DISCLAIMER.split(".")[0].lower() not in full_draft.lower():
                tail += "\n\n---\n" + DRAFT_DISCLAIMER
            if "ai-generated" not in full_draft.lower() and "ai-assisted" not in full_draft.lower():
                tail += (" " if tail else "\n\n---\n") + AI_GENERATED_NOTICE
            if tail:
                yield json.dumps({"content": tail})
    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        yield json.dumps({"content":
            "\n\n⚠ The answer engine hit a problem (" + str(e)[:300] + "). Showing the cited sources "
            "below — please retry, or check the model key / connection."})
    # Always append the cited-sources summary (provisions + judgments) so the chat shows them.
    if sources_footer:
        yield json.dumps({"content": sources_footer})
    yield json.dumps({"done": True})
