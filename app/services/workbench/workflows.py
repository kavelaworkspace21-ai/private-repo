"""
Workbench workflow registry — the product definitions (pack §5, encoded exactly).

Each workflow declares:
  intake     — required-question schema shown in INTAKE (question-first, always)
  sections   — the ordered artifact section names (these ARE the product)
  law_sections — sections that assert legal propositions; the citation hard-gate
                 blocks them if they carry no citation from the retrieved grounding
  kind       — which plan meter a generation consumes (research_query | draft)
  needs_upload — tools that require a document (live in WB-02+; visible, not runnable)

Prompts referencing these schemas live in /ai/prompts/workbench/ and are data,
reviewed at Gate G8 — never self-certified.
"""
from app.models.billing import KIND_RESEARCH, KIND_DRAFT


def q(key: str, question: str, required: bool = True, hint: str = "") -> dict:
    return {"key": key, "question": question, "required": required, "hint": hint}


WORKFLOWS: dict[str, dict] = {

    # ── W1 · Case File Analysis (needs uploads — WB-02/03) ──────────────────
    "case_file_analysis": {
        "label": "Case File Analysis",
        "tagline": "Upload a case file → 15-section senior-advocate analysis",
        "icon": "file-search",
        "kind": KIND_RESEARCH,
        "needs_upload": True,
        "upload_ready": True,           # WB-03: live — sessions accept upload_ids
        "intake": [
            q("parties_side", "Who are the parties, and which side are you appearing for?"),
            q("court_stage", "Which court is the matter in, and at what stage?"),
            q("relief_context", "What relief is sought / what outcome does your client want?"),
        ],
        "sections": [
            "Facts Summary", "Chronology of Events", "Legal Issues", "Questions of Fact",
            "Questions of Law", "Strengths of the Case", "Weaknesses of the Case",
            "Missing Evidence", "Limitation Issues", "Jurisdiction Issues",
            "Maintainability Concerns", "Possible Remedies",
            "Litigation Risk Factors (qualitative)", "Further Documents Required",
            "Suggested Litigation Strategy",
        ],
        "law_sections": ["Legal Issues", "Questions of Law", "Limitation Issues",
                         "Jurisdiction Issues", "Maintainability Concerns", "Possible Remedies"],
        # Pack §3.3 — sections that must cite the uploaded file with [p.N] page refs.
        "file_sections": ["Facts Summary", "Chronology of Events", "Questions of Fact",
                          "Strengths of the Case", "Weaknesses of the Case", "Missing Evidence",
                          "Further Documents Required", "Suggested Litigation Strategy"],
    },

    # ── W2 · Guided Drafting (upgrade path — WB-07 wires the editor) ────────
    "guided_drafting": {
        "label": "Guided Drafting",
        "tagline": "Question-first drafting with a pre-draft checklist",
        "icon": "pen-line",
        "kind": KIND_DRAFT,
        "needs_upload": False,
        "intake": [
            q("document_needed", "What document do you need drafted?"),
            q("parties_facts", "Who are the parties, and what are the key facts (with dates)?"),
            q("court_jurisdiction", "Which court/authority will receive it, and why does it have jurisdiction?"),
            q("relief_sought", "What exact relief/outcome must the document achieve?"),
            q("documents_available", "What supporting documents do you hold?", required=False),
        ],
        "sections": [
            "Missing Facts", "Missing Documents", "Procedural Requirements",
            "Legal Issues", "Drafting Strategy",
        ],
        "law_sections": ["Procedural Requirements", "Legal Issues"],
    },

    # ── W3 · Deep Research (WB-04: + Kanoon authorities + Legal Memo variant) ──
    "deep_research": {
        "label": "Deep Research",
        "tagline": "Questions → provisions → authorities → court-ready note (or a legal memo)",
        "icon": "scale",
        "kind": KIND_RESEARCH,
        "needs_upload": False,
        "intake": [
            q("jurisdiction", "Which jurisdiction (state / court system) applies?"),
            q("statute", "Which statute(s) or area of law is the question under?"),
            q("stage", "What stage are the proceedings at (pre-filing, trial, appeal…)?"),
            q("relief", "What relief is sought?"),
            q("issues", "State the legal issue(s) you need researched, applied to your facts."),
            q("output_type", "Output — leave blank for the full research pack, or type "
                             "\"memo\" for a structured legal memo.", required=False),
        ],
        "sections": [
            "Research Questions", "Search Keywords", "Relevant Statutory Provisions",
            "Procedural Provisions", "Leading Supreme Court Authorities",
            "Relevant High Court Authorities", "Conflicting Views",
            "Current Legal Position", "Court-Ready Research Note",
        ],
        "law_sections": ["Relevant Statutory Provisions", "Procedural Provisions",
                         "Current Legal Position", "Court-Ready Research Note"],
        # WB-04: sections that may cite ONLY live-retrieved authorities, by [An] marker.
        "authority_sections": ["Leading Supreme Court Authorities",
                               "Relevant High Court Authorities", "Conflicting Views"],
        # Sections whose content must carry the good-law treatment caveat.
        "caveat_sections": ["Current Legal Position"],
        # Alternate output type (pack §5 W3): topic → structured memo with references.
        "variants": {
            "memo": {
                "label": "Legal Memo",
                "sections": [
                    "Memo Heading", "Questions Presented", "Short Answer",
                    "Statutory Framework", "Discussion of Authorities",
                    "Conflicting Views", "Conclusion & Current Position", "References",
                ],
                "law_sections": ["Statutory Framework", "Conclusion & Current Position"],
                "authority_sections": ["Discussion of Authorities", "Conflicting Views",
                                       "References"],
                "caveat_sections": ["Conclusion & Current Position"],
            },
        },
    },

    # ── W4 · Judgment Analyzer (needs upload/Kanoon pick — WB-05) ───────────
    "judgment_analyzer": {
        "label": "Judgment Analyzer",
        "tagline": "Ratio, quotables, how to use it — and how it gets distinguished",
        "icon": "gavel",
        "kind": KIND_RESEARCH,
        "needs_upload": True,
        "upload_ready": True,           # WB-05: live — upload a judgment or pick from Kanoon
        "kanoon_pick": True,            # Step-0 also accepts an Indian Kanoon doc id/link
        "intake": [
            q("side", "Which side are you appearing for?"),
            q("relief", "What relief are you seeking?"),
            q("issue", "What issue are you researching this judgment for?"),
            q("court", "Which court are you before?"),
            q("intended_use", "How do you intend to use this judgment (support / distinguish / anticipate)?"),
        ],
        "sections": [
            "One-Page Summary", "Material Facts", "Issues Before the Court",
            "Ratio Decidendi", "Obiter Dicta", "Final Holding",
            "Key Quotable Passages", "Practical Application",
            "How This Judgment Helps My Case", "How Opposing Counsel May Distinguish It",
            "Weaknesses in Relying Upon It", "Court-Ready Research Note",
            "2-Minute Courtroom Explanation",
        ],
        # Grounding is the JUDGMENT itself (pack WB-05: "grounding limited to the judgment
        # + cited law") — the analytical spine must cite the document by page.
        "law_sections": [],
        "file_sections": ["One-Page Summary", "Material Facts", "Issues Before the Court",
                          "Ratio Decidendi", "Obiter Dicta", "Final Holding",
                          "Practical Application", "How This Judgment Helps My Case",
                          "How Opposing Counsel May Distinguish It",
                          "Weaknesses in Relying Upon It"],
        # WB-05's signature gate: quotables must be EXACT substrings with pinpoint refs.
        "verbatim_sections": ["Key Quotable Passages"],
        "caveat_sections": ["Practical Application", "How This Judgment Helps My Case",
                            "Court-Ready Research Note"],
    },

    # ── W5 · Argument Studio (founder-requested) ─────────────────────────────
    "argument_studio": {
        "label": "Argument Studio",
        "tagline": "Full argument packs, hearing notes, and Judge Mode",
        "icon": "message-square",
        "kind": KIND_DRAFT,
        "needs_upload": False,
        "intake": [
            q("facts", "State the facts of the case (with dates)."),
            q("procedural_history", "What is the procedural history so far?"),
            q("relief", "What relief are you seeking?"),
            q("applicable_law", "Which statutes/provisions do you consider applicable?"),
            q("evidence", "What evidence is available?"),
            q("opponents_case", "What is the opponent's case, as best you know it?"),
            q("stage", "What stage is the matter at, and when is the hearing?"),
        ],
        "sections": [
            "Theory of the Case", "Issues for Determination", "Strongest Facts",
            "Relevant Statutory Provisions", "Leading Authorities",
            "Sequence of Oral Arguments", "Anticipated Questions from the Bench",
            "Opposing Counsel's Best Arguments", "Rebuttals to Each",
            "Vulnerabilities in My Case", "Relief-Oriented Submissions",
            "5-Minute Hearing Note", "15-Minute Detailed Argument Note",
            "One-Page Court Note", "Judge Mode: The 10 Toughest Questions",
        ],
        "law_sections": ["Relevant Statutory Provisions", "Relief-Oriented Submissions"],
        # Three entry modes (pack §5 W5): Matter / uploaded files / selected citations.
        "entry_modes": True,
        # Both sides get the SAME citation discipline (pack §3.6): the advocate's authorities,
        # the opponent's best arguments, and every Judge-Mode response cite live/selected judgments.
        "authority_sections": ["Leading Authorities", "Opposing Counsel's Best Arguments",
                               "Judge Mode: The 10 Toughest Questions"],
        # Uploaded case-detail facts must be page-anchored where used.
        "file_sections": ["Strongest Facts", "Vulnerabilities in My Case"],
        "caveat_sections": ["Leading Authorities"],
    },

    # ── W6 · Chat with Case File (needs uploads — WB-02) ────────────────────
    "chat_with_file": {
        "label": "Chat with Case File",
        "tagline": "Ask any PDF questions; generate a List of Dates & Events",
        "icon": "file-text",
        "kind": KIND_RESEARCH,
        "needs_upload": False,          # WB-02: live — has its own upload panel
        "upload_tool": True,
        "intake": [
            q("purpose", "What do you want from this file (questions, summary, list of dates)?"),
        ],
        "sections": ["Answer"],
        "law_sections": [],
    },
}


# Test-only workflows: exercise the engine's gates deterministically, without an LLM.
# Never shown in the hub (hidden=True); the registry is the single source of truth.
WORKFLOWS["_gate_probe_research"] = {
    "label": "Gate Probe (research)", "tagline": "engine test", "icon": "beaker",
    "kind": KIND_RESEARCH, "needs_upload": False, "hidden": True,
    "intake": [q("topic", "Topic?"), q("detail", "Detail?", required=False)],
    "sections": ["Overview", "Legal Position", "Note"],
    "law_sections": ["Legal Position"],
}
WORKFLOWS["_gate_probe_draft"] = {
    "label": "Gate Probe (draft)", "tagline": "engine test", "icon": "beaker",
    "kind": KIND_DRAFT, "needs_upload": False, "hidden": True,
    "intake": [q("topic", "Topic?")],
    "sections": ["Overview"],
    "law_sections": [],
}


def get_workflow(workflow_type: str) -> dict | None:
    return WORKFLOWS.get(workflow_type)


def visible_workflows() -> list[dict]:
    out = []
    for wtype, w in WORKFLOWS.items():
        if w.get("hidden"):
            continue
        out.append({"type": wtype, "label": w["label"], "tagline": w["tagline"],
                    "icon": w["icon"], "needs_upload": w["needs_upload"],
                    "upload_tool": bool(w.get("upload_tool")),
                    "upload_ready": bool(w.get("upload_ready")),
                    "kind": w["kind"], "questions": len(w["intake"]),
                    "sections": len(w["sections"])})
    return out
