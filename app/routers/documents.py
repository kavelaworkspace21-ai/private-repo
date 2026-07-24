from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.auth.dependencies import require_matter_write
from app.services.tenancy import (
    current_tenant_id, get_owned_case, get_owned_child, scoped_children, write_audit,
)
from app.services import storage
from app.schemas.document import DocumentCreate, DocumentOut, DocumentVersionOut

router = APIRouter()


# ── List / metadata create (kept) ───────────────────────────────────────────────
@router.get("/", response_model=list[DocumentOut])
def list_documents(case_id: int | None = None, db: Session = Depends(get_db),
                   tenant_id: int = Depends(current_tenant_id)):
    return scoped_children(db, Document, tenant_id, case_id).order_by(Document.id).all()


@router.post("/", response_model=DocumentOut, status_code=201)
def create_document(payload: DocumentCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_matter_write)):
    get_owned_case(payload.case_id, user.tenant_id, db)
    doc = Document(**payload.model_dump(), tenant_id=user.tenant_id)
    db.add(doc); db.commit(); db.refresh(doc)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_document", entity="Document", entity_id=doc.id)
    return doc


# ── Real upload (creates Document + version 1) ──────────────────────────────────
@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(case_id: int = Form(...), notes: str | None = Form(None),
                          file: UploadFile = File(...),
                          db: Session = Depends(get_db),
                          user: User = Depends(require_matter_write)):
    get_owned_case(case_id, user.tenant_id, db)
    data = await file.read()
    try:
        info = storage.save_file(user.tenant_id, file.filename, data)
    except (storage.FileTooLarge, storage.FileTypeNotAllowed) as e:
        raise HTTPException(400, str(e))

    doc = Document(tenant_id=user.tenant_id, case_id=case_id,
                   filename=file.filename, file_path=info["storage_path"], notes=notes)
    db.add(doc); db.flush()
    _add_version(db, doc, info, file, user.id)   # version 1
    db.commit(); db.refresh(doc)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="upload_document", entity="Document", entity_id=doc.id)
    return doc


# ── Add a new version to an existing document ───────────────────────────────────
@router.post("/{doc_id}/versions", response_model=DocumentVersionOut, status_code=201)
async def add_version(doc_id: int, file: UploadFile = File(...),
                      db: Session = Depends(get_db),
                      user: User = Depends(require_matter_write)):
    doc = get_owned_child(db, Document, doc_id, user.tenant_id, "Document")
    data = await file.read()
    try:
        info = storage.save_file(user.tenant_id, file.filename, data)
    except (storage.FileTooLarge, storage.FileTypeNotAllowed) as e:
        raise HTTPException(400, str(e))
    ver = _add_version(db, doc, info, file, user.id)
    doc.file_path = info["storage_path"]
    doc.filename = file.filename
    db.commit(); db.refresh(ver)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="version_document", entity="Document", entity_id=doc.id,
                detail=f"v{ver.version_no}")
    return ver


@router.get("/{doc_id}/versions", response_model=list[DocumentVersionOut])
def list_versions(doc_id: int, db: Session = Depends(get_db),
                  tenant_id: int = Depends(current_tenant_id)):
    get_owned_child(db, Document, doc_id, tenant_id, "Document")
    return (db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc_id)
            .order_by(DocumentVersion.version_no.desc()).all())


@router.get("/{doc_id}/download")
def download_document(doc_id: int, version: int | None = None,
                     db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    get_owned_child(db, Document, doc_id, tenant_id, "Document")
    q = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_id)
    ver = (q.filter(DocumentVersion.version_no == version).first() if version
           else q.order_by(DocumentVersion.version_no.desc()).first())
    if not ver:
        raise HTTPException(404, "No stored file for this document")
    data = storage.read_file(ver.storage_path)
    if data is None:
        raise HTTPException(410, "Stored file is no longer available")
    return Response(
        content=data,
        media_type=ver.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{ver.original_filename}"'},
    )


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db),
                tenant_id: int = Depends(current_tenant_id)):
    return get_owned_child(db, Document, doc_id, tenant_id, "Document")


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_matter_write)):
    doc = get_owned_child(db, Document, doc_id, user.tenant_id, "Document")
    for ver in db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_id).all():
        storage.delete_file(ver.storage_path)
        db.delete(ver)
    db.delete(doc); db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_document", entity="Document", entity_id=doc_id)


# ── helper ──────────────────────────────────────────────────────────────────────
def _add_version(db: Session, doc: Document, info: dict, file: UploadFile, user_id: int):
    last = (db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_no.desc()).first())
    ver = DocumentVersion(
        tenant_id=doc.tenant_id, document_id=doc.id,
        version_no=(last.version_no + 1) if last else 1,
        original_filename=file.filename, storage_path=info["storage_path"],
        content_type=file.content_type, size_bytes=info["size"],
        sha256=info["sha256"], uploaded_by=user_id,
    )
    db.add(ver); db.flush()
    return ver
