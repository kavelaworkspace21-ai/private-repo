"""
Advocate Workbench API (pack §4) — tenant-scoped, JWT, every mutation audited.

The router is deliberately thin: every rule lives in the engine so all six tools
inherit the same discipline. Uploads (WB-02) will extend this surface.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.observability import internal_error
from app.db.session import get_db
from app.models.user import User
from app.models.workbench import WorkflowArtifact
from app.auth.dependencies import require_ai_user, get_current_user
from app.services.ratelimit import ai_limiter
from app.services.workbench import engine
from app.services.workbench.workflows import visible_workflows, get_workflow

router = APIRouter()


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except engine.WorkflowError as e:
        raise HTTPException(e.status_code, e.detail)


# ── Catalogue ─────────────────────────────────────────────────────────────────
@router.get("/workflows")
def workflows(_: User = Depends(get_current_user)):
    return visible_workflows()


# ── Sessions ──────────────────────────────────────────────────────────────────
class SessionCreate(BaseModel):
    workflow_type: str = Field(min_length=1, max_length=40)
    matter_id: int | None = None
    upload_ids: list[int] = Field(default_factory=list, max_length=5)
    citation_tids: list[str] = Field(default_factory=list, max_length=8)


class AnswersIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    proceed_with_assumptions: bool = False

    model_config = {"extra": "forbid"}


@router.post("/sessions", status_code=201)
def create_session(body: SessionCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_ai_user)):
    s = _run(engine.create_session, db, user, body.workflow_type, body.matter_id,
             body.upload_ids, body.citation_tids)
    return engine.session_payload(db, s)


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    s = _run(engine.get_owned_session, db, session_id, user.tenant_id)
    return engine.session_payload(db, s)


@router.post("/sessions/{session_id}/answers")
def submit_answers(session_id: int, body: AnswersIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    if len(body.answers) > 40:
        raise HTTPException(422, "Too many answers (max 40).")
    s = _run(engine.get_owned_session, db, session_id, user.tenant_id)
    s = _run(engine.submit_answers, db, user, s, body.answers, body.proceed_with_assumptions)
    return engine.session_payload(db, s)


@router.post("/sessions/{session_id}/generate", dependencies=[Depends(ai_limiter)])
def generate(session_id: int, db: Session = Depends(get_db),
             user: User = Depends(require_ai_user)):
    s = _run(engine.get_owned_session, db, session_id, user.tenant_id)
    artifact = _run(engine.generate, db, user, s)
    return _artifact_payload(db, artifact)


# ── Artifacts ─────────────────────────────────────────────────────────────────
def _artifact_payload(db: Session, a: WorkflowArtifact) -> dict:
    wf = get_workflow(a.artifact_type) or {}
    return {
        "id": a.id, "session_id": a.session_id, "artifact_type": a.artifact_type,
        "label": wf.get("label", a.artifact_type), "version": a.version,
        "sections": a.content_json, "citations": a.citations_json,
        "confidence": a.confidence, "review_status": a.review_status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    a = _run(engine.get_owned_artifact, db, artifact_id, user.tenant_id)
    return _artifact_payload(db, a)


@router.get("/artifacts")
def list_artifacts(matter_id: int | None = None, artifact_type: str | None = None,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Artifact library — this IS the research history (filter artifact_type=deep_research)."""
    q = db.query(WorkflowArtifact).filter(WorkflowArtifact.tenant_id == user.tenant_id)
    if artifact_type:
        q = q.filter(WorkflowArtifact.artifact_type == artifact_type)
    if matter_id is not None:
        from app.models.workbench import WorkflowSession
        sess_ids = [sid for (sid,) in db.query(WorkflowSession.id).filter(
            WorkflowSession.tenant_id == user.tenant_id,
            WorkflowSession.matter_id == matter_id).all()]
        q = q.filter(WorkflowArtifact.session_id.in_(sess_ids or [-1]))
    rows = q.order_by(WorkflowArtifact.id.desc()).limit(100).all()
    return [_artifact_payload(db, a) for a in rows]


# ── WB-02: uploads + file-grounded chat + List of Dates ───────────────────────
from app.services.workbench import uploads as up_svc


def _run_up(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except up_svc.UploadError as e:
        raise HTTPException(e.status_code, e.detail)


def _upload_payload(u) -> dict:
    return {"id": u.id, "filename": u.filename, "page_count": u.page_count,
            "retention_policy": u.retention_policy,
            "delete_after": u.delete_after.isoformat() if u.delete_after else None,
            "created_at": u.created_at.isoformat() if u.created_at else None}


@router.post("/uploads", status_code=201)
async def upload_file(file: UploadFile = File(...), session_id: int | None = Form(None),
                      db: Session = Depends(get_db), user: User = Depends(require_ai_user)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")
    u = _run_up(up_svc.save_upload, db, user, file.filename or "upload", data, session_id)
    return _upload_payload(u)


class KanoonPick(BaseModel):
    tid: str = Field(min_length=1, max_length=200)   # bare doc id or full Kanoon URL


@router.post("/uploads/from-kanoon", status_code=201)
def upload_from_kanoon(body: KanoonPick, db: Session = Depends(get_db),
                       user: User = Depends(require_ai_user)):
    """WB-05: materialise an Indian Kanoon judgment as an upload (same retention,
    same anchors) so the Judgment Analyzer can source from a picked case."""
    u = _run_up(up_svc.save_kanoon_judgment, db, user, body.tid)
    return _upload_payload(u)


@router.get("/uploads")
def list_uploads(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.workbench import WorkbenchUpload
    rows = (db.query(WorkbenchUpload)
              .filter(WorkbenchUpload.tenant_id == user.tenant_id)
              .order_by(WorkbenchUpload.id.desc()).limit(50).all())
    return [_upload_payload(u) for u in rows]


class FileQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=4000)


@router.post("/uploads/{upload_id}/chat", dependencies=[Depends(ai_limiter)])
def chat_with_file(upload_id: int, body: FileQuestion, db: Session = Depends(get_db),
                   user: User = Depends(require_ai_user)):
    """FILE-grounded Q&A: answers only from the uploaded document, page-anchored.
    A question the file can't answer refuses deterministically — and costs nothing."""
    u = _run_up(up_svc.get_owned_upload, db, upload_id, user.tenant_id)
    from app.models.billing import KIND_RESEARCH
    from app.services.entitlements import enforce_quota, meter
    enforce_quota(db, user, KIND_RESEARCH)
    result = _run_up(up_svc.answer_from_file, db, user, u, body.question)
    if not result["refused"]:
        meter(db, user, KIND_RESEARCH)          # a refusal costs the advocate nothing
    return result


@router.post("/uploads/{upload_id}/list-of-dates")
def generate_list_of_dates(upload_id: int, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """Deterministic court chronology — extraction, not generation; no plan units."""
    u = _run_up(up_svc.get_owned_upload, db, upload_id, user.tenant_id)
    pages = _run_up(up_svc.load_pages, u)
    return up_svc.list_of_dates(pages)


class SaveUploadToMatter(BaseModel):
    case_id: int


@router.post("/uploads/{upload_id}/save-to-matter", status_code=201)
def save_upload_to_matter(upload_id: int, body: SaveUploadToMatter,
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    u = _run_up(up_svc.get_owned_upload, db, upload_id, user.tenant_id)
    doc = _run_up(up_svc.save_to_matter, db, user, u, body.case_id)
    return {"document_id": doc.id, "case_id": body.case_id,
            "message": "Saved to the matter — the file now lives with the case and "
                       "no longer auto-deletes."}


# ── WB-08: artifacts become practice objects ──────────────────────────────────
def _artifact_export_text(db: Session, a: WorkflowArtifact) -> str:
    """Rendered artifact + the mandatory footer: AI-assistance disclosure + review
    disclaimer (pack WB-08: every export carries both)."""
    from app.ai.safety import AI_GENERATED_NOTICE, DRAFT_DISCLAIMER
    wf = get_workflow(a.artifact_type) or {}
    body = engine.artifact_markdown(a, wf.get("label", a.artifact_type))
    footer = ""
    if DRAFT_DISCLAIMER.split(".")[0].lower() not in body.lower():
        footer += "\n\n---\n" + DRAFT_DISCLAIMER
    footer += "\n" + AI_GENERATED_NOTICE
    return body + footer


class ArtifactExport(BaseModel):
    format: str = Field(pattern=r"^(docx|pdf)$")


@router.post("/artifacts/{artifact_id}/export")
def export_artifact(artifact_id: int, body: ArtifactExport, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    a = _run(engine.get_owned_artifact, db, artifact_id, user.tenant_id)
    from fastapi.responses import Response
    from app.routers.ai_drafting import _build_docx, _build_pdf, _safe_filename
    text = _artifact_export_text(db, a)
    try:
        if body.format == "docx":
            data, media = _build_docx(text), \
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            data, media = _build_pdf(text), "application/pdf"
    except Exception as e:
        raise internal_error(e, status_code=500, action="Export")
    from app.services.tenancy import write_audit
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id, action="workbench_artifact_export",
                entity="WorkflowArtifact", entity_id=a.id, detail=f"{a.artifact_type}.{body.format}")
    fname = _safe_filename(f"workbench_{a.artifact_type}", body.format)
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


class ArtifactToMatter(BaseModel):
    case_id: int


@router.post("/artifacts/{artifact_id}/save-to-matter", status_code=201)
def artifact_to_matter(artifact_id: int, body: ArtifactToMatter, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """The artifact becomes a versioned case Document (pack WB-08)."""
    a = _run(engine.get_owned_artifact, db, artifact_id, user.tenant_id)
    from app.services.tenancy import get_owned_case, write_audit
    get_owned_case(body.case_id, user.tenant_id, db)
    from app.services import storage
    from app.models.document import Document
    from app.models.document_version import DocumentVersion
    wf = get_workflow(a.artifact_type) or {}
    text = _artifact_export_text(db, a)
    fname = f"{wf.get('label', a.artifact_type).replace(' ', '_')}_v{a.version}.txt"
    info = storage.save_file(user.tenant_id, fname, text.encode("utf-8"))
    doc = Document(tenant_id=user.tenant_id, case_id=body.case_id, filename=fname,
                   file_path=info["storage_path"], notes=f"Workbench artifact #{a.id}")
    db.add(doc); db.flush()
    db.add(DocumentVersion(tenant_id=user.tenant_id, document_id=doc.id, version_no=1,
                           original_filename=fname, storage_path=info["storage_path"],
                           content_type="text/plain", size_bytes=info["size"],
                           sha256=info["sha256"], uploaded_by=user.id))
    db.commit(); db.refresh(doc)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="workbench_artifact_to_matter", entity="Document", entity_id=doc.id,
                detail=f"artifact={a.id} case={body.case_id}")
    return {"document_id": doc.id, "case_id": body.case_id,
            "message": "Saved to the matter as a versioned document."}


class TasksFromStrategy(BaseModel):
    case_id: int
    days_ahead: int = Field(default=7, ge=1, le=90)


_TASK_LINE_RE = None  # compiled lazily


@router.post("/artifacts/{artifact_id}/create-tasks", status_code=201)
def create_tasks_from_strategy(artifact_id: int, body: TasksFromStrategy,
                               db: Session = Depends(get_db),
                               user: User = Depends(get_current_user)):
    """Strategy items → Court Diary tasks (pack WB-08). Free tier's read-only diary
    rule applies here too — this is a diary WRITE."""
    from app.services.entitlements import diary_write_gate
    diary_write_gate(user, db)                       # 402 for free tier, by the same rule
    a = _run(engine.get_owned_artifact, db, artifact_id, user.tenant_id)
    from app.services.tenancy import get_owned_case, write_audit
    get_owned_case(body.case_id, user.tenant_id, db)

    import re as _re
    from datetime import date, timedelta
    from app.models.diary_task import DiaryTask
    source_sections = ("Suggested Litigation Strategy", "Further Documents Required",
                      "Missing Evidence", "Drafting Strategy")
    lines: list[str] = []
    for sec in (a.content_json or []):
        if sec.get("name") in source_sections and not sec.get("blocked"):
            for raw in (sec.get("content") or "").splitlines():
                # Only LIST-marked lines are items — prose sentences are not tasks.
                if not _re.match(r"^\s*(?:[-\*•]|\d+[\.\)])\s+", raw):
                    continue
                ln = _re.sub(r"^\s*(?:[-\*•]|\d+[\.\)])\s+", "", raw).strip()
                if 12 <= len(ln) <= 300 and "[removed" not in ln and "withheld" not in ln:
                    lines.append(ln)
    lines = lines[:10]                               # capped — a diary, not a dump
    if not lines:
        raise HTTPException(422, "No actionable strategy items found in this artifact.")
    due = date.today() + timedelta(days=body.days_ahead)
    created = []
    for ln in lines:
        t = DiaryTask(tenant_id=user.tenant_id, case_id=body.case_id,
                      title=ln[:200], due_date=due)
        db.add(t); db.flush()
        created.append(t.id)
    db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="workbench_tasks_from_strategy", entity="WorkflowArtifact",
                entity_id=a.id, detail=f"case={body.case_id} tasks={len(created)}")
    return {"created": len(created), "task_ids": created, "due_date": due.isoformat(),
            "message": f"{len(created)} diary task(s) created from the artifact's strategy items."}


@router.post("/artifacts/{artifact_id}/approve")
def approve_artifact(artifact_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """The ONLY way an artifact leaves review status — explicit advocate approval,
    audited (pack WB-08; CLAUDE.md §2.4). Clerks cannot approve."""
    from app.models.user import UserRole
    if user.role not in (UserRole.advocate, UserRole.firm_admin):
        raise HTTPException(403, "Only an advocate or firm admin may approve an artifact.")
    a = _run(engine.get_owned_artifact, db, artifact_id, user.tenant_id)
    from datetime import datetime, timezone
    from app.ai.safety import DRAFT_STATUS_APPROVED
    from app.services.tenancy import write_audit
    a.review_status = DRAFT_STATUS_APPROVED
    a.approved_by = user.id
    a.approved_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(a)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="workbench_artifact_approved", entity="WorkflowArtifact", entity_id=a.id)
    return _artifact_payload(db, a)


class SaveToReview(BaseModel):
    case_id: int | None = None


@router.post("/artifacts/{artifact_id}/save-to-review", status_code=201)
def save_to_review(artifact_id: int, body: SaveToReview, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Feed the artifact into the existing governed review queue (/drafts):
    versioning, diff, explicit advocate approval, DOCX/PDF export — all reused."""
    a = _run(engine.get_owned_artifact, db, artifact_id, user.tenant_id)
    wf = get_workflow(a.artifact_type) or {}
    if body.case_id is not None:
        from app.services.tenancy import get_owned_case
        get_owned_case(body.case_id, user.tenant_id, db)
    from app.models.generated_draft import GeneratedDraft
    from app.services.tenancy import write_audit
    content = engine.artifact_markdown(a, wf.get("label", a.artifact_type))
    d = GeneratedDraft(tenant_id=user.tenant_id, created_by=user.id, case_id=body.case_id,
                       document_type=f"workbench_{a.artifact_type}",
                       title=f"{wf.get('label', a.artifact_type)} — v{a.version}",
                       content=content)
    db.add(d); db.commit(); db.refresh(d)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="workbench_saved_to_review", entity="GeneratedDraft", entity_id=d.id,
                detail=f"artifact={a.id}")
    return {"draft_id": d.id, "status": d.status,
            "message": "Saved to the review queue — approve and export it from Drafts."}
