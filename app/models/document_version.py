from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DocumentVersion(Base):
    """
    An immutable stored version of a document (CLAUDE.md §5: every document write creates
    a DocumentVersion). Provenance: storage path + SHA-256 + size + who/when.
    """
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    uploaded_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
