"""
Saved drafts + advocate review workflow (CLAUDE.md section 2.4).

A draft is stored as DRAFT_FOR_ADVOCATE_REVIEW. It becomes ADVOCATE_APPROVED only via
the explicit /approve action by a write-permitted role. There is no other path to
'approved' — this enforces "no draft is final without advocate approval".
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.generated_draft import GeneratedDraft
from app.models.draft_version import GeneratedDraftVersion
from app.auth.dependencies import require_matter_write
from app.services.tenancy import current_tenant_id, get_owned_case, write_audit
from app.ai.safety import (
    DRAFT_STATUS_REVIEW, DRAFT_STATUS_APPROVED, ensure_draft_disclaimer,
)
from app.schemas.draft import DraftSaveRequest, DraftOut, DraftEdit, DraftVersionOut

router = APIRouter()


def _owned_draft(draft_id: int, tenant_id: int, db: Session) -> GeneratedDraft:
    d = db.get(GeneratedDraft, draft_id)
    if not d or d.tenant_id != tenant_id:
        raise HTTPException(404, "Draft not found")
    return d


def _snapshot(db: Session, draft: GeneratedDraft, user_id: int):
    """Append an immutable version snapshot of the draft's current content."""
    last = (db.query(GeneratedDraftVersion)
            .filter(GeneratedDraftVersion.draft_id == draft.id)
            .order_by(GeneratedDraftVersion.version_no.desc()).first())
    ver = GeneratedDraftVersion(
        tenant_id=draft.tenant_id, draft_id=draft.id,
        version_no=(last.version_no + 1) if last else 1,
        title=draft.title, content=draft.content, created_by=user_id,
    )
    db.add(ver); db.flush()
    return ver


@router.get("/", response_model=list[DraftOut])
def list_drafts(db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    return (
        db.query(GeneratedDraft)
        .filter(GeneratedDraft.tenant_id == tenant_id)
        .order_by(GeneratedDraft.id.desc())
        .all()
    )


@router.post("/", response_model=DraftOut, status_code=201)
def save_draft(payload: DraftSaveRequest, db: Session = Depends(get_db),
               user: User = Depends(require_matter_write)):
    if payload.case_id is not None:
        get_owned_case(payload.case_id, user.tenant_id, db)  # ownership check
    draft = GeneratedDraft(
        tenant_id=user.tenant_id,
        created_by=user.id,
        case_id=payload.case_id,
        document_type=payload.document_type,
        title=payload.title,
        content=ensure_draft_disclaimer(payload.content),
        status=DRAFT_STATUS_REVIEW,   # always starts in review
    )
    db.add(draft); db.flush()
    _snapshot(db, draft, user.id)          # version 1
    db.commit(); db.refresh(draft)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="save_draft", entity="GeneratedDraft", entity_id=draft.id)
    return draft


@router.get("/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: int, db: Session = Depends(get_db),
              tenant_id: int = Depends(current_tenant_id)):
    return _owned_draft(draft_id, tenant_id, db)


@router.patch("/{draft_id}", response_model=DraftOut)
def edit_draft(draft_id: int, payload: DraftEdit, db: Session = Depends(get_db),
               user: User = Depends(require_matter_write)):
    """
    Edit a draft's content → new version snapshot. Because the content changed, any prior
    advocate approval no longer applies, so the draft is re-opened as DRAFT_FOR_ADVOCATE_REVIEW
    (CLAUDE.md §2.4 — only the approved content is 'final').
    """
    draft = _owned_draft(draft_id, user.tenant_id, db)
    draft.content = ensure_draft_disclaimer(payload.content)
    if payload.title:
        draft.title = payload.title
    draft.status = DRAFT_STATUS_REVIEW
    draft.approved_by = None
    draft.approved_at = None
    ver = _snapshot(db, draft, user.id)
    db.commit(); db.refresh(draft)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="edit_draft", entity="GeneratedDraft", entity_id=draft.id,
                detail=f"v{ver.version_no}; re-opened for review")
    return draft


@router.get("/{draft_id}/versions", response_model=list[DraftVersionOut])
def list_versions(draft_id: int, db: Session = Depends(get_db),
                  tenant_id: int = Depends(current_tenant_id)):
    _owned_draft(draft_id, tenant_id, db)
    return (db.query(GeneratedDraftVersion)
            .filter(GeneratedDraftVersion.draft_id == draft_id)
            .order_by(GeneratedDraftVersion.version_no.desc()).all())


@router.post("/{draft_id}/revert/{version_no}", response_model=DraftOut)
def revert_draft(draft_id: int, version_no: int, db: Session = Depends(get_db),
                 user: User = Depends(require_matter_write)):
    """Restore a previous version's content as a new version (re-opens for review)."""
    draft = _owned_draft(draft_id, user.tenant_id, db)
    target = (db.query(GeneratedDraftVersion)
              .filter(GeneratedDraftVersion.draft_id == draft_id,
                      GeneratedDraftVersion.version_no == version_no).first())
    if not target:
        raise HTTPException(404, "Version not found")
    draft.content = target.content
    draft.title = target.title
    draft.status = DRAFT_STATUS_REVIEW
    draft.approved_by = None
    draft.approved_at = None
    ver = _snapshot(db, draft, user.id)
    db.commit(); db.refresh(draft)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="revert_draft", entity="GeneratedDraft", entity_id=draft.id,
                detail=f"reverted to v{version_no} as v{ver.version_no}")
    return draft


@router.post("/{draft_id}/approve", response_model=DraftOut)
def approve_draft(draft_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_matter_write)):
    """The ONLY way a draft becomes ADVOCATE_APPROVED."""
    draft = _owned_draft(draft_id, user.tenant_id, db)
    draft.status = DRAFT_STATUS_APPROVED
    draft.approved_by = user.id
    draft.approved_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(draft)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="approve_draft", entity="GeneratedDraft", entity_id=draft.id)
    return draft


@router.delete("/{draft_id}", status_code=204)
def delete_draft(draft_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_matter_write)):
    draft = _owned_draft(draft_id, user.tenant_id, db)
    db.query(GeneratedDraftVersion).filter(
        GeneratedDraftVersion.draft_id == draft_id).delete(synchronize_session=False)
    db.delete(draft); db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_draft", entity="GeneratedDraft", entity_id=draft_id)
