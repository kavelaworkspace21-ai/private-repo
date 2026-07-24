from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class GeneratedDraftVersion(Base):
    """
    An immutable snapshot of a draft's content (CLAUDE.md §5: every document write creates a
    version). Editing a draft creates a new version and re-opens it for advocate review.
    """
    __tablename__ = "generated_draft_versions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    draft_id: Mapped[int] = mapped_column(ForeignKey("generated_drafts.id"), index=True, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
