"""
Workbench workflow engine (pack §4, WB-01) — the reusable spine under every tool.

State machine:  INTAKE → CONFIRM → GENERATING → COMPLETE   (+ REFUSED)

Gates enforced HERE, once, for every workflow:
  • Question-first: generation is impossible from INTAKE. Either every required
    intake question is answered, or the advocate explicitly proceeds with stated
    assumptions — which are then printed into the artifact itself.
  • Citation hard-gate per section: a law-bearing section whose text carries no
    citation found in the retrieved grounding is BLOCKED (content replaced by a
    refusal note), never silently shown.
  • No prediction: banned-phrase screen runs over every section.
  • Entitlements: a generation consumes one plan unit (research or draft) —
    checked before any model work, recorded only when generation proceeds.
  • AuditLog on every state-changing mutation; artifacts start in review status.
"""
import json
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.workbench import (
    WorkflowSession, WorkflowArtifact,
    STATE_INTAKE, STATE_CONFIRM, STATE_GENERATING, STATE_COMPLETE, STATE_REFUSED,
)
from app.models.user import User
from app.services.workbench.workflows import get_workflow
from app.services.tenancy import write_audit

logger = logging.getLogger(__name__)

REFUSAL_SECTION_NOTE = (
    "⚠ This section asserted a legal position without a citation from the retrieved "
    "sources, so it was withheld (no source, no answer). Refine the intake facts or "
    "consult the Legal Library directly."
)


class WorkflowError(Exception):
    def __init__(self, status_code: int, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(str(detail))


# ── Session lifecycle ─────────────────────────────────────────────────────────
def create_session(db: Session, user: User, workflow_type: str,
                   matter_id: int | None = None,
                   upload_ids: list[int] | None = None,
                   citation_tids: list[str] | None = None) -> WorkflowSession:
    wf = get_workflow(workflow_type)
    if not wf:
        raise WorkflowError(404, "Unknown workflow.")
    upload_ids = upload_ids or []
    # Entry mode (c): selected judgments become the ONLY authority set (stored under a
    # reserved key the client can never set through the answers endpoint).
    citation_tids = [re.sub(r"\D", "", str(t))[:20] for t in (citation_tids or [])][:8]
    citation_tids = [t for t in citation_tids if t]
    if wf.get("needs_upload"):
        if not wf.get("upload_ready"):
            raise WorkflowError(409, f"{wf['label']} arrives with a later Workbench update. "
                                     "The other tools are live.")
        if not upload_ids:
            raise WorkflowError(409, f"{wf['label']} works on a document — upload the case "
                                     "file first, then start the analysis.")
    if matter_id is not None:
        from app.services.tenancy import get_owned_case
        get_owned_case(matter_id, user.tenant_id, db)     # ownership or 404

    # Validate upload ownership BEFORE creating anything (cross-tenant = 404).
    from app.services.workbench import uploads as up_svc
    ups = []
    for uid in upload_ids[:5]:
        try:
            ups.append(up_svc.get_owned_upload(db, uid, user.tenant_id))
        except up_svc.UploadError as e:
            raise WorkflowError(e.status_code, e.detail)

    intake = {"_selected_citations": citation_tids} if citation_tids else {}
    s = WorkflowSession(tenant_id=user.tenant_id, user_id=user.id,
                        matter_id=matter_id, workflow_type=workflow_type, intake_json=intake)
    db.add(s); db.commit(); db.refresh(s)
    for u in ups:
        u.session_id = s.id
    if ups:
        db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="workbench_session_created", entity="WorkflowSession", entity_id=s.id,
                detail=f"{workflow_type} uploads={[u.id for u in ups]} "
                       f"citations={len(citation_tids)}")
    return s


def session_uploads(db: Session, s: WorkflowSession):
    from app.models.workbench import WorkbenchUpload
    return (db.query(WorkbenchUpload)
              .filter(WorkbenchUpload.session_id == s.id,
                      WorkbenchUpload.tenant_id == s.tenant_id).all())


def get_owned_session(db: Session, session_id: int, tenant_id: int) -> WorkflowSession:
    s = (db.query(WorkflowSession)
           .filter(WorkflowSession.id == session_id,
                   WorkflowSession.tenant_id == tenant_id).first())
    if not s:
        raise WorkflowError(404, "Session not found.")
    return s


def missing_required(s: WorkflowSession) -> list[dict]:
    wf = get_workflow(s.workflow_type)
    answered = s.intake_json or {}
    return [q for q in wf["intake"]
            if q["required"] and not str(answered.get(q["key"], "")).strip()]


def session_payload(db: Session, s: WorkflowSession) -> dict:
    wf = get_workflow(s.workflow_type)
    artifact = (db.query(WorkflowArtifact)
                  .filter(WorkflowArtifact.session_id == s.id)
                  .order_by(WorkflowArtifact.version.desc()).first())
    return {
        "id": s.id, "workflow_type": s.workflow_type, "label": wf["label"],
        "state": s.state, "matter_id": s.matter_id,
        "questions": wf["intake"],
        "answers": {k: v for k, v in (s.intake_json or {}).items() if not k.startswith("_")},
        "selected_citations": (s.intake_json or {}).get("_selected_citations", []),
        "missing": [q["key"] for q in missing_required(s)],
        "assumptions": s.assumptions_json or [],
        "sections_planned": resolve_schema(wf, s)["sections"],
        "artifact_id": artifact.id if artifact else None,
        "uploads": [{"id": u.id, "filename": u.filename, "page_count": u.page_count}
                    for u in session_uploads(db, s)],
    }


def submit_answers(db: Session, user: User, s: WorkflowSession,
                   answers: dict, proceed_with_assumptions: bool = False) -> WorkflowSession:
    if s.state in (STATE_GENERATING,):
        raise WorkflowError(409, "Generation already in progress.")
    merged = dict(s.intake_json or {})
    for k, v in (answers or {}).items():
        key = str(k)[:64]
        if key.startswith("_"):
            continue                               # reserved keys are server-set, never client
        merged[key] = str(v)[:8000]                # same abuse caps as drafting
    s.intake_json = merged

    missing = missing_required(s)
    if not missing:
        s.state = STATE_CONFIRM
        s.assumptions_json = []
    elif proceed_with_assumptions:
        # The question-first discipline allows an explicit override — but the gaps
        # become stated assumptions, printed at the top of the artifact.
        s.assumptions_json = [
            f"No answer was given to: “{q['question']}” — proceeding on stated facts alone."
            for q in missing
        ]
        s.state = STATE_CONFIRM
    else:
        s.state = STATE_INTAKE
    db.commit(); db.refresh(s)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="workbench_intake_updated", entity="WorkflowSession", entity_id=s.id,
                detail=f"state={s.state}, missing={len(missing)}")
    return s


# ── Grounding + generation ────────────────────────────────────────────────────
# "Will I win?" and friends: prohibited output, refused up-front (pack §3.2 + CLAUDE.md §1).
_PREDICTION_PROBE_RE = re.compile(
    r"will\s+(?:i|we|my client)\s+win|what\s+are\s+(?:my|our)\s+chances|"
    r"chances?\s+of\s+(?:winning|success)|probabilit\w*\s+of\s+(?:winning|success)|"
    r"win\s+(?:percentage|probability|rate)|likelihood\s+of\s+(?:winning|success)",
    re.IGNORECASE)

PREDICTION_REFUSAL = (
    "Juriscite does not predict case outcomes, chances, or probabilities — for anyone. "
    "That line protects you: outcome prediction is barred for court processes by the draft "
    "SC AI-in-Courts Regulations and is incompatible with source-grounded practice. "
    "The analysis instead prepares you qualitatively: strengths, weaknesses, missing "
    "evidence, and strategy — all tied to the file and the law. Please rephrase the "
    "flagged answer without asking for a prediction."
)


def _prediction_probe(s: WorkflowSession) -> bool:
    return any(_PREDICTION_PROBE_RE.search(str(v) or "") for v in (s.intake_json or {}).values())


def _file_grounding(db: Session, s: WorkflowSession, budget: int = 9000) -> str:
    """Page-marked excerpts of the session's uploads — the FILE side of grounding.
    Pages are truncated fairly so even a large file shows every part of itself."""
    from app.services.workbench import uploads as up_svc
    ups = session_uploads(db, s)
    if not ups:
        return ""
    parts, spent = [], 0
    for u in ups:
        try:
            pages = up_svc.load_pages(u)
        except up_svc.UploadError:
            continue
        per_page = max(400, budget // max(1, len(pages) * len(ups)))
        for p in pages:
            if spent >= budget:
                break
            take = p["text"][:per_page]
            if take.strip():
                parts.append(f"[p.{p['page']}] {take}")
                spent += len(take)
    return "\n\n".join(parts)


def resolve_schema(wf: dict, s: WorkflowSession) -> dict:
    """Variant-aware schema (WB-04): e.g. Deep Research's 'memo' output type swaps the
    section set. Falls back to the workflow's base schema."""
    base = {"label": wf["label"], "sections": wf["sections"],
            "law_sections": wf.get("law_sections", []),
            "file_sections": wf.get("file_sections", []),
            "authority_sections": wf.get("authority_sections", []),
            "caveat_sections": wf.get("caveat_sections", []),
            "verbatim_sections": wf.get("verbatim_sections", [])}
    choice = str((s.intake_json or {}).get("output_type", "")).strip().lower()
    variant = (wf.get("variants") or {}).get(choice[:16])
    if not variant and choice.startswith("memo"):
        variant = (wf.get("variants") or {}).get("memo")
    if variant:
        base.update({k: v for k, v in variant.items() if k in base})
    return base


def _authorities_for(s: WorkflowSession, limit: int = 8) -> list[dict]:
    """Judgments the artifact may reference — each with a REAL link and the good-law caveat.
    The model refers to them by [An] marker and can never mint a case name.

    Entry mode (c) — Argument Studio: if the advocate SELECTED specific citations, those
    (and only those) are the authority set, grounding the arguments in the chosen judgments
    plus the statute library (pack §5 W5). Otherwise, a live Kanoon search from the intake."""
    from app.ai import case_law
    answers = s.intake_json or {}
    selected = answers.get("_selected_citations") or []
    cards: list[dict] = []
    if selected:
        for tid in selected[:limit]:
            tid = str(tid)
            doc = None
            try:
                doc = case_law.fetch_document(tid)
            except Exception as e:
                logger.warning(f"Selected-citation fetch failed ({tid}): {e}")
            # The Kanoon URL is deterministic from the id, so the link is real even if the
            # metadata fetch is unavailable — we keep the authority, we don't invent a name.
            cards.append({
                "title": (doc or {}).get("title", "") or "(selected judgment)",
                "court": (doc or {}).get("court", ""), "date": (doc or {}).get("date", ""),
                "url": f"https://indiankanoon.org/doc/{tid}/", "good_law": "unverified"})
    else:
        try:
            query = " ".join(str(answers.get(k, "")) for k in
                             ("statute", "issues", "relief", "applicable_law"))[:200]
            cards = case_law.search_cases(query.strip(), limit=limit) or []
        except Exception as e:
            logger.warning(f"Workbench authorities unavailable: {e}")
            cards = []
    out = []
    for i, c in enumerate(cards, start=1):
        if not c.get("url"):
            continue                      # no link → not an authority we can hand a court
        out.append({"ref": f"A{i}", "title": c.get("title", ""), "court": c.get("court", ""),
                    "date": c.get("date", ""), "url": c["url"],
                    "good_law": c.get("good_law", "unverified")})
    return out


NO_AUTHORITIES_NOTE = ("No live authorities were retrieved for this point (case-law service "
                       "unavailable or no matching judgments). The statutory position above "
                       "still governs; run the search again later for judgments.")
NO_CONFLICT_NOTE = ("The retrieved authorities do not disclose a conflict with sources on "
                    "both sides, so no conflicting-views analysis is presented.")
GOOD_LAW_CAVEAT_LINE = ("_Good-law status of the cited judgments is unverified — confirm "
                        "treatment (followed/distinguished/overruled) before relying._")

_AUTH_REF_RE = re.compile(r"\[(A\d+)\]")


def _apply_authority_gates(sections: list[dict], authority_sections: list[str],
                           caveat_sections: list[str], auths: list[dict],
                           available_law: set[str] | None = None) -> None:
    """Authorities discipline (pack WB-04/06): [An] markers must resolve to retrieved/selected
    judgments; unresolvable markers are stripped and flagged; Conflicting Views needs sources
    on BOTH sides; the good-law caveat is guaranteed on position sections. A cited section with
    no judgment survives ONLY if it still rests on a verified statute (so a Judge-Mode response
    grounded in a section, not a case, is not wrongly wiped)."""
    from app.ai.safety import extract_citations
    available_law = available_law or set()
    valid = {a["ref"]: a for a in auths}
    for sec in sections:
        name = sec["name"]
        if name in authority_sections:
            sec["grounding"] = "LAW"
            content = sec.get("content") or ""
            if not auths:
                # No judgments. Keep the section only if it rests on a verified statute;
                # strip any invented [An] markers; otherwise say so honestly.
                law_cited = extract_citations(content) & available_law
                for r in set(_AUTH_REF_RE.findall(content)):
                    content = content.replace(f"[{r}]", "[removed: unverified authority]")
                if law_cited and name != "Conflicting Views":
                    sec["content"], sec["authorities"] = content, []
                else:
                    sec["content"], sec["authorities"] = NO_AUTHORITIES_NOTE, []
                continue
            refs = _AUTH_REF_RE.findall(sec.get("content") or "")
            unknown = [r for r in refs if r not in valid]
            if unknown:
                for r in unknown:                      # never show an unverifiable reference
                    sec["content"] = sec["content"].replace(f"[{r}]", "[removed: unverified authority]")
            used = [valid[r] for r in dict.fromkeys(refs) if r in valid]
            if name == "Conflicting Views" and len(used) < 2:
                sec["content"] = NO_CONFLICT_NOTE
                sec["authorities"] = []
                continue
            # Content that referenced nothing real gets the honest note — unless it still
            # rests on a verified statute (a section-grounded argument survives), and a
            # stripped fabrication stays visible AS stripped so the reader sees it.
            law_cited = extract_citations(sec.get("content", "")) & available_law
            if not used and not unknown and not law_cited and sec.get("content", "").strip():
                sec["content"] = NO_AUTHORITIES_NOTE
            sec["authorities"] = used
        # Look for the caveat itself, not any "good law" wording — a scrubbed good-law
        # ASSERTION must still receive the caveat, not masquerade as one.
        if name in caveat_sections and sec.get("content", "").strip() \
                and "confirm treatment" not in sec["content"].lower():
            sec["content"] = sec["content"].rstrip() + "\n\n" + GOOD_LAW_CAVEAT_LINE


VERBATIM_REMOVED = "[removed: not verbatim in the source]"
VERBATIM_BLOCKED_NOTE = (
    "⚠ Every passage offered here failed verbatim verification against the judgment text, "
    "so the section was withheld. Paraphrase presented as quotation is never shown."
)
_QUOTE_RE = re.compile(r"[\"“]([^\"“”]{15,600})[\"”]")
# Good-law assertions need treatment data we don't have — they never survive as claims.
_GOODLAW_ASSERT_RE = re.compile(
    r"(?:is|remains|still|continues to be)\s+(?:good\s+law|binding\s+precedent)", re.IGNORECASE)


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("“", '"').replace("”", '"')
                  .replace("’", "'").replace("‘", "'")).strip()


def _apply_verbatim_gates(sections: list[dict], verbatim_sections: list[str],
                          pages: list[dict]) -> None:
    """WB-05's signature gate: a 'Key Quotable Passage' must be an EXACT substring of the
    source (whitespace/smart-quote normalised) AND actually sit on the page it pinpoints.
    Failed quotes are replaced visibly; a section with no surviving quote is withheld.
    Also scrubs good-law assertions everywhere — we hold no treatment data."""
    page_norm = {p["page"]: _norm_ws(p["text"]) for p in pages}
    full_norm = " ".join(page_norm.values())

    for sec in sections:
        if sec.get("content"):
            sec["content"] = _GOODLAW_ASSERT_RE.sub("[good-law status unverified]", sec["content"])
        if sec["name"] not in verbatim_sections:
            continue
        sec["grounding"] = "FILE"
        content = sec.get("content") or ""
        survivors = 0
        for m in list(_QUOTE_RE.finditer(content)):
            quote = _norm_ws(m.group(1))
            tail = content[m.end():m.end() + 12]
            page_m = re.match(r"\s*\[p\.(\d+)\]", tail)
            claimed = int(page_m.group(1)) if page_m else None
            ok = (quote in page_norm.get(claimed, "")) if claimed else (quote in full_norm)
            if ok and claimed:
                survivors += 1
            else:
                content = content.replace(m.group(0), VERBATIM_REMOVED, 1)
        if survivors == 0 and content.strip():
            sec["content"] = VERBATIM_BLOCKED_NOTE
            sec["blocked"] = True
        else:
            sec["content"] = content
            sec["blocked"] = False


def _grounding_for(s: WorkflowSession) -> str:
    """Retrieved verbatim statute text — the ONLY law the artifact may cite."""
    try:
        from app.ai import rag
        answers = s.intake_json or {}
        query = " ".join(str(v) for v in answers.values())[:400]
        exact = rag.retrieve_by_section(query)
        broad = rag.retrieve(query)
        return ((exact + "\n\n") if exact else "") + (broad or "")
    except Exception as e:
        logger.warning(f"Workbench grounding unavailable: {e}")
        return ""


def _parse_sections(text: str, wanted: list[str]) -> list[dict]:
    """Split '## Section Name' markdown into the declared schema order."""
    found: dict[str, str] = {}
    current, buf = None, []
    for line in text.splitlines():
        m = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if m:
            if current is not None:
                found[current] = "\n".join(buf).strip()
            current, buf = m.group(1).strip(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        found[current] = "\n".join(buf).strip()

    def _match(name: str) -> str | None:
        for k in found:
            if k.lower().startswith(name.lower()[:24]) or name.lower().startswith(k.lower()[:24]):
                return k
        return None

    out = []
    for name in wanted:
        k = _match(name)
        out.append({"name": name, "content": found.get(k, "").strip() if k else ""})
    return out


FILE_REFUSAL_NOTE = (
    "⚠ This section had to cite the uploaded file with page references [p.N] and did not, "
    "so it was withheld rather than shown unverifiable. Regenerate, or check the file covers "
    "this ground."
)

_PAGE_REF_RE = re.compile(r"\[p\.\d+\]")


def _apply_gates(sections: list[dict], law_sections: list[str], grounding: str,
                 file_sections: list[str] | None = None,
                 has_file: bool = False) -> tuple[list[dict], list[str], bool]:
    """Per-section gates (pack §3.3): LAW sections need a citation verified against the
    retrieved statute; FILE sections need [p.N] page refs into the uploaded document;
    every section passes the banned-phrase screen. BOTH = both rules."""
    from app.ai.safety import extract_citations, sanitize_answer
    available = set(extract_citations(grounding))
    file_sections = file_sections or []
    all_citations: set[str] = set()
    any_blocked = False

    for sec in sections:
        content = sanitize_answer(sec["content"])          # banned phrases / prediction language
        sec["content"] = content
        cited = set(extract_citations(content))
        is_law = sec["name"] in law_sections
        is_file = has_file and sec["name"] in file_sections
        sec["grounding"] = ("BOTH" if (is_law and is_file) else
                            "LAW" if is_law else
                            "FILE" if is_file else "NONE")
        sec["blocked"] = False

        if is_law:
            verified = cited & available if available else set()
            if content and not verified:
                sec["content"] = REFUSAL_SECTION_NOTE
                sec["blocked"] = True
                any_blocked = True
            else:
                all_citations |= verified
        if is_file and not sec["blocked"] and content and not _PAGE_REF_RE.search(content):
            sec["content"] = FILE_REFUSAL_NOTE
            sec["blocked"] = True
            any_blocked = True
        if not is_law:
            all_citations |= (cited & available)
        if not sec["content"]:
            sec["content"] = "_(no content generated for this section)_"
    return sections, sorted(all_citations), any_blocked


def _llm_generate(wf: dict, s: WorkflowSession, grounding: str, file_ctx: str = "",
                  schema: dict | None = None, auths: list[dict] | None = None) -> str:
    """One grounded call producing every section as '## <name>' markdown."""
    from app.ai.llm_config import ai_config
    cfg = ai_config()
    if not cfg["api_key"]:
        raise WorkflowError(503, "The AI engine isn't connected (no model key on this server).")

    schema = schema or resolve_schema(wf, s)
    from app.ai.safety import DRAFT_DISCLAIMER
    answers = s.intake_json or {}
    intake_lines = "\n".join(f"- {q['question']}\n  Answer: {answers.get(q['key'], '(not provided)')}"
                             for q in wf["intake"])
    assumptions = "\n".join(f"- {a}" for a in (s.assumptions_json or [])) or "(none)"
    section_list = "\n".join(f"## {name}" for name in schema["sections"])

    file_rule = file_block = ""
    if file_ctx:
        file_rule = ("6. Factual statements about the case MUST cite the uploaded file with "
                     "inline page references exactly as [p.N], taken from the FILE EXCERPTS "
                     "markers. A fact you cannot anchor to a page does not go in.\n")
        file_block = f"\n\nFILE EXCERPTS (the uploaded case file, page-marked):\n{file_ctx}"

    verbatim_rule = ""
    if schema["verbatim_sections"]:
        names = ", ".join(schema["verbatim_sections"])
        verbatim_rule = (f"8. In {names}: every passage MUST be copied EXACTLY, "
                         "character-for-character, from the FILE EXCERPTS, wrapped in "
                         "double quotes and immediately followed by its pinpoint page "
                         "reference, e.g. \"...exact text...\" [p.3]. Never paraphrase "
                         "inside quotation marks — a non-verbatim quote is discarded.\n")

    auth_rule = auth_block = ""
    if auths:
        listing = "\n".join(f"[{a['ref']}] {a['title']} — {a['court']}, {a['date']}"
                            for a in auths)
        auth_rule = ("7. Judgments may be referenced ONLY from the RETRIEVED AUTHORITIES "
                     "list, by marker, e.g. [A1]. NEVER name a case that is not on the list. "
                     "Conflicting Views must present BOTH sides, each anchored to its own "
                     "[An]; if the list shows no true conflict, say so plainly.\n")
        auth_block = f"\n\nRETRIEVED AUTHORITIES (the only judgments you may reference):\n{listing}"
    elif schema["authority_sections"]:
        auth_rule = ("7. NO live judgments were retrieved. In the authorities sections, say "
                     "plainly that no authorities were retrieved — never name cases from "
                     "memory.\n")

    system = (
        "You are a senior Indian advocate's meticulous junior, preparing an internal "
        f"work product: {schema['label']}. Write in precise, court-appropriate English.\n\n"
        "ABSOLUTE RULES (violations make the output unusable):\n"
        "1. Output EVERY section below, in order, each starting with its '## ' heading, "
        "exactly as named.\n"
        "2. Legal propositions may cite ONLY provisions present in the RETRIEVED LAW "
        "block. Cite as 'Section N of the <Act>'. If the retrieved law does not cover a "
        "point, say so plainly instead of citing from memory.\n"
        "3. NEVER predict outcomes: no win/loss language, no percentages, no probabilities, "
        "no scores. Strengths/weaknesses are qualitative preparation notes tied to facts.\n"
        "4. Never invent facts. A fact not given in the intake is written as [●].\n"
        f"5. End the final section with: \"{DRAFT_DISCLAIMER}\"\n"
        f"{file_rule}{auth_rule}{verbatim_rule}\n"
        f"SECTIONS (exact headings, in order):\n{section_list}\n\n"
        f"RETRIEVED LAW (the only citable sources):\n{grounding or '(nothing retrieved)'}"
        f"{file_block}{auth_block}"
    )
    user_msg = (f"INTAKE:\n{intake_lines}\n\nSTATED ASSUMPTIONS:\n{assumptions}\n\n"
                f"Produce the complete {schema['label']} now.")

    from openai import OpenAI
    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=240, max_retries=2)
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user_msg}],
        max_tokens=4096, temperature=0.1,
    )
    return resp.choices[0].message.content or ""


def _probe_generate(wf: dict, s: WorkflowSession, grounding: str) -> str:
    """Deterministic generator for the hidden _gate_probe_* workflows (tests, no LLM).
    Intentionally emits an UNCITED legal-position section when the intake asks for it,
    so the tests can prove the hard-gate blocks it."""
    answers = s.intake_json or {}
    topic = answers.get("topic", "the stated topic")
    cite_mode = answers.get("detail", "")
    from app.ai.safety import extract_citations
    available = list(extract_citations(grounding))
    legal = (f"The position on {topic} is governed by Section {available[0]}."
             if (available and cite_mode != "uncited") else
             f"The law clearly favours this position on {topic}.")   # uncited on purpose
    parts = [f"## Overview\nPreparation notes on {topic}.",
             f"## Legal Position\n{legal}",
             "## Note\nDraft for advocate review. Verify facts, jurisdiction, limitation, "
             "court rules, and latest case law before filing."]
    return "\n\n".join(p for p in parts if p.split("\n")[0].replace("## ", "") in wf["sections"])


def generate(db: Session, user: User, s: WorkflowSession) -> WorkflowArtifact:
    wf = get_workflow(s.workflow_type)

    # Question-first, always (pack §3.1): generation is impossible from INTAKE.
    if s.state == STATE_INTAKE:
        raise WorkflowError(409, {
            "error": "intake_incomplete",
            "missing": [q["key"] for q in missing_required(s)],
            "message": "Answer the required intake questions first (or explicitly proceed "
                       "with stated assumptions)."})
    if s.state == STATE_GENERATING:
        raise WorkflowError(409, "Generation already in progress.")

    # No outcome prediction, ever (pack §3.2): a probe in the intake is refused up-front,
    # before any plan unit is consumed or any model is called.
    if _prediction_probe(s):
        raise WorkflowError(422, {"error": "prediction_refused", "message": PREDICTION_REFUSAL})

    # Entitlements: one plan unit per generation, checked before any model work.
    from app.services.entitlements import enforce_quota, meter
    enforce_quota(db, user, wf["kind"])

    s.state = STATE_GENERATING
    db.commit()

    try:
        schema = resolve_schema(wf, s)
        grounding = _grounding_for(s)
        file_ctx = _file_grounding(db, s)
        auths = _authorities_for(s) if schema["authority_sections"] else []
        if s.workflow_type.startswith("_gate_probe"):
            raw = _probe_generate(wf, s, grounding)
        else:
            raw = _llm_generate(wf, s, grounding, file_ctx, schema=schema, auths=auths)

        sections = _parse_sections(raw, schema["sections"])
        sections, citations, any_blocked = _apply_gates(
            sections, schema["law_sections"], grounding,
            file_sections=schema["file_sections"], has_file=bool(file_ctx))
        from app.ai.safety import extract_citations as _xc
        _apply_authority_gates(sections, schema["authority_sections"],
                               schema["caveat_sections"], auths,
                               available_law=set(_xc(grounding)))
        if schema["verbatim_sections"]:
            from app.services.workbench import uploads as up_svc
            pages = []
            for u in session_uploads(db, s):
                try:
                    pages.extend(up_svc.load_pages(u))
                except up_svc.UploadError:
                    pass
            _apply_verbatim_gates(sections, schema["verbatim_sections"], pages)

        # Assumptions are part of the artifact — the reader must see what was NOT known.
        if s.assumptions_json:
            sections.insert(0, {"name": "Stated Assumptions", "grounding": "NONE", "blocked": False,
                                "content": "\n".join(f"- {a}" for a in s.assumptions_json)})

        law_total = len(schema["law_sections"])
        law_blocked = sum(1 for x in sections if x.get("blocked"))
        if law_total and law_blocked == law_total:
            # Every legal section failed grounding → the artifact refuses rather than guesses.
            s.state = STATE_REFUSED
            confidence = "LOW"
        else:
            s.state = STATE_COMPLETE
            confidence = "LOW" if any_blocked else ("HIGH" if citations else "MEDIUM")

        prev = (db.query(WorkflowArtifact)
                  .filter(WorkflowArtifact.session_id == s.id)
                  .order_by(WorkflowArtifact.version.desc()).first())
        artifact = WorkflowArtifact(
            tenant_id=s.tenant_id, session_id=s.id, artifact_type=s.workflow_type,
            version=(prev.version + 1) if prev else 1,
            content_json=sections, citations_json=citations, confidence=confidence,
        )
        db.add(artifact)
        db.commit(); db.refresh(artifact); db.refresh(s)

        meter(db, user, wf["kind"])            # the unit is consumed only on a real run
        write_audit(db, tenant_id=s.tenant_id, user_id=user.id,
                    action="workbench_artifact_generated", entity="WorkflowArtifact",
                    entity_id=artifact.id,
                    detail=f"{s.workflow_type} v{artifact.version} "
                           f"{'REFUSED' if s.state == STATE_REFUSED else confidence}")
        return artifact
    except WorkflowError:
        s.state = STATE_CONFIRM      # recoverable — the advocate can retry
        db.commit()
        raise
    except Exception as e:
        s.state = STATE_CONFIRM
        db.commit()
        logger.warning(f"Workbench generation failed: {e}")
        raise WorkflowError(502, f"Generation failed ({str(e)[:200]}). Nothing was charged "
                                 "against your plan — please retry.")


def get_owned_artifact(db: Session, artifact_id: int, tenant_id: int) -> WorkflowArtifact:
    a = (db.query(WorkflowArtifact)
           .filter(WorkflowArtifact.id == artifact_id,
                   WorkflowArtifact.tenant_id == tenant_id).first())
    if not a:
        raise WorkflowError(404, "Artifact not found.")
    return a


def artifact_markdown(a: WorkflowArtifact, label: str) -> str:
    """Render an artifact to markdown — feeds the existing review/export pipeline."""
    lines = [f"# {label}", ""]
    for sec in (a.content_json or []):
        lines += [f"## {sec['name']}", "", sec.get("content", ""), ""]
    return "\n".join(lines)
