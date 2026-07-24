from sqlalchemy import String, Text, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.ai.safety import DRAFT_STATUS_REVIEW


class GeneratedDraft(Base):
    """
    A drafted legal document saved for advocate review (CLAUDE.md section 2.4).
    Starts as DRAFT_FOR_ADVOCATE_REVIEW; only an explicit advocate approval may move it
    to ADVOCATE_APPROVED. No code path sets 'approved' without that action.
    """
    __tablename__ = "generated_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)        # user id
    case_id: Mapped[int | None] = mapped_column(Integer, index=True)        # optional link

    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(40), default=DRAFT_STATUS_REVIEW, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(Integer)               # user id
    approved_at: Mapped[DateTime | None] = mapped_column(DateTime)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
