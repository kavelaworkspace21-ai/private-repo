"""
Account & data-principal rights (DPDP Act 2023 + SC draft AI-in-Courts Regs 2026 reg. 10).

- GET  /api/account/export   → right to access / portability: all of the user's tenant data as JSON
- DELETE /api/account        → right to erasure: delete the user's own account + tenant data
- GET  /api/account/privacy  → the data-protection statement (no training on client data, etc.)

Everything is scoped to the caller's own tenant. Deletion is irreversible and requires an
explicit confirmation flag; it is audited (the audit is written before the data is removed).
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.client import Client
from app.models.case import Case
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.generated_draft import GeneratedDraft
from app.models.notification import Notification
from app.models.consent import ConsentRecord
from app.models.audit import AuditLog
from app.auth.dependencies import get_current_user
from app.services import storage
from app.services.privacy import (
    NO_TRAINING_STATEMENT, TERMS_VERSION, PRIVACY_VERSION, RETENTION_POLICY,
)

router = APIRouter()


def _rows(db, model, tenant_id):
    return [
        {c.name: getattr(r, c.name) for c in model.__table__.columns}
        for r in db.query(model).filter(model.tenant_id == tenant_id).all()
    ]


@router.get("/privacy")
def privacy_statement(_: User = Depends(get_current_user)):
    return {
        "no_training": NO_TRAINING_STATEMENT,
        "terms_version": TERMS_VERSION,
        "privacy_version": PRIVACY_VERSION,
        "retention": RETENTION_POLICY,
        "your_rights": ["access/export (GET /api/account/export)",
                        "erasure (DELETE /api/account)"],
    }


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None


@router.patch("/profile")
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Update the caller's own display profile (name / phone). Audited."""
    from app.services.tenancy import write_audit
    if body.full_name is not None and body.full_name.strip():
        user.full_name = body.full_name.strip()
    if body.phone is not None:
        user.phone = body.phone.strip() or None
    db.commit()
    db.refresh(user)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_profile", entity="User", entity_id=user.id)
    return {"full_name": user.full_name, "phone": user.phone,
            "email": user.email, "role": user.role.value}


@router.get("/export")
def export_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """DPDP right to access — everything we hold for this user's tenant, as JSON."""
    tid = user.tenant_id
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {c.name: getattr(user, c.name) for c in User.__table__.columns
                 if c.name != "hashed_password"},
        "tenant_id": tid,
        "clients": _rows(db, Client, tid),
        "cases": _rows(db, Case, tid),
        "documents": _rows(db, Document, tid),
        "drafts": _rows(db, GeneratedDraft, tid),
        "notifications": _rows(db, Notification, tid),
        "consents": _rows(db, ConsentRecord, tid),
    }


class DeleteRequest(BaseModel):
    confirm: bool = False


@router.delete("/", status_code=200)
def delete_my_account(body: DeleteRequest, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """DPDP right to erasure — irreversibly delete the caller's account + tenant data."""
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true to permanently delete your account and data.")
    tid = user.tenant_id

    # Audit the erasure first (the audit rows are then deleted with the tenant).
    db.add(AuditLog(tenant_id=tid, user_id=user.id, action="account_deleted",
                    entity="Tenant", entity_id=tid, detail="DPDP erasure"))
    db.commit()

    # 1) Remove stored files for this tenant — documents AND workbench extractions.
    for ver in db.query(DocumentVersion).filter(DocumentVersion.tenant_id == tid).all():
        storage.delete_file(ver.storage_path)
    _erase_workbench_files(db, tid)

    # 2) Delete tenant-scoped rows (children of Case cascade via ORM relationships)
    db.query(DocumentVersion).filter(DocumentVersion.tenant_id == tid).delete(synchronize_session=False)
    db.query(GeneratedDraft).filter(GeneratedDraft.tenant_id == tid).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.tenant_id == tid).delete(synchronize_session=False)
    db.query(ConsentRecord).filter(ConsentRecord.tenant_id == tid).delete(synchronize_session=False)
    for client in db.query(Client).filter(Client.tenant_id == tid).all():
        db.delete(client)              # cascades to cases → hearings/fees/diary/docs/etc.
    db.commit()
    # Any cases not linked through a deleted client (defensive)
    for case in db.query(Case).filter(Case.tenant_id == tid).all():
        db.delete(case)
    # 3) AI history, activity trail, workbench, and request records.
    #    These were previously MISSED. Chat messages and activity previews carry client
    #    facts verbatim ("anticipatory bail for Ramesh Kumar in the Acme matter"), so an
    #    erasure that left them behind made "your data was deleted" untrue.
    _erase_ai_and_activity(db, tid)
    _erase_tenant_records(db, tid)

    # 4) Financial records are ANONYMISED, not deleted — Indian tax/GST rules require
    #    invoice retention, which survives an erasure request. Stripping the identifiers
    #    keeps the statutory record without keeping the person.
    _anonymise_financial_records(db, tid)

    db.query(AuditLog).filter(AuditLog.tenant_id == tid).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id == tid).delete(synchronize_session=False)
    db.query(Tenant).filter(Tenant.id == tid).delete(synchronize_session=False)
    db.commit()
    return {"status": "deleted", "message": "Your account and all associated data were deleted."}


# ── Erasure helpers ─────────────────────────────────────────────────────────────
# Split out so each class of data is visible and testable. tests/test_erasure_completeness.py
# walks the schema and fails if ANY tenant/user-scoped table still holds rows afterwards, so a
# newly added table cannot silently inherit "kept forever".

def _erase_workbench_files(db: Session, tenant_id: int) -> None:
    """Delete extracted-text / anchor files written for workbench uploads."""
    try:
        from app.models.workbench import WorkbenchUpload
    except Exception:
        return
    rows = db.query(WorkbenchUpload).filter(WorkbenchUpload.tenant_id == tenant_id).all()
    for up in rows:
        for ref in (up.extracted_text_ref, up.anchors_ref):
            if ref:
                try:
                    storage.delete_file(ref)
                except Exception:
                    # A missing file must not abort an erasure request; the row still goes.
                    pass


def _erase_ai_and_activity(db: Session, tenant_id: int) -> None:
    """Chat conversations, their messages, and the activity trail.

    `Conversation.user_id` declares ondelete="CASCADE", but SQLite runs with
    PRAGMA foreign_keys=0, so that cascade fires on PostgreSQL and silently does nothing
    on SQLite. Deleting explicitly makes erasure behave identically on both.
    """
    user_ids = [u.id for u in db.query(User).filter(User.tenant_id == tenant_id).all()]
    if not user_ids:
        return

    try:
        from app.models.ai_chat import AiMessage, Conversation
        conv_ids = [c.id for c in db.query(Conversation)
                    .filter(Conversation.user_id.in_(user_ids)).all()]
        if conv_ids:
            db.query(AiMessage).filter(
                AiMessage.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(
            Conversation.user_id.in_(user_ids)).delete(synchronize_session=False)
    except Exception:
        pass

    try:
        from app.models.user_activity import UserActivity
        db.query(UserActivity).filter(
            UserActivity.user_id.in_(user_ids)).delete(synchronize_session=False)
    except Exception:
        pass
    db.commit()


def _erase_tenant_records(db: Session, tenant_id: int) -> None:
    """Every remaining tenant-scoped table that holds user or client data."""
    candidates = [
        ("app.models.workbench", "WorkflowArtifact"),
        ("app.models.workbench", "WorkbenchUpload"),
        ("app.models.workbench", "WorkflowSession"),
        ("app.models.draft_version", "GeneratedDraftVersion"),
        ("app.models.data_rights", "DataRightsRequest"),
        ("app.models.misuse_report", "MisuseReport"),
        ("app.models.billing", "WebhookEvent"),
    ]
    import importlib
    for module_path, cls_name in candidates:
        try:
            model = getattr(importlib.import_module(module_path), cls_name)
        except Exception:
            continue
        if hasattr(model, "tenant_id"):
            db.query(model).filter(
                model.tenant_id == tenant_id).delete(synchronize_session=False)
    db.commit()


def _anonymise_financial_records(db: Session, tenant_id: int) -> None:
    """Strip personal identifiers from records kept for statutory financial retention.

    The rows survive (tax law), the person does not. Only clears columns that identify a
    human — amounts, dates and tax fields are the reason the record is retained at all.
    """
    import importlib

    PII_COLUMNS = {"name", "full_name", "email", "phone", "address", "gstin",
                   "billing_name", "billing_email", "customer_name", "customer_email",
                   "razorpay_customer_id", "contact"}

    for module_path, cls_name in (("app.models.billing", "Invoice"),
                                  ("app.models.billing", "Subscription"),
                                  ("app.models.billing", "UsageEvent")):
        try:
            model = getattr(importlib.import_module(module_path), cls_name)
        except Exception:
            continue
        if not hasattr(model, "tenant_id"):
            continue
        updates = {c: None for c in PII_COLUMNS
                   if hasattr(model, c) and getattr(model.__table__.c, c, None) is not None
                   and getattr(model.__table__.c, c).nullable}
        if updates:
            db.query(model).filter(
                model.tenant_id == tenant_id).update(updates, synchronize_session=False)
    db.commit()
