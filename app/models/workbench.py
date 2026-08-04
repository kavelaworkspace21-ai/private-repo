"""
Advocate Workbench (LSAI-WB pack §4) — session, artifact, upload.

Doctrine carried in the schema itself:
  • every table is tenant-scoped (CLAUDE.md §5);
  • an artifact is born DRAFT_FOR_ADVOCATE_REVIEW and can only leave that state
    through the explicit approval flow (§2.4);
  • uploads carry their retention policy so the 7-day scratch auto-delete is a
    property of the row, not a convention someone has to remember.
"""

from sqlalchemy import String, Integer, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.ai.safety import DRAFT_STATUS_REVIEW

# Workflow session states (pack §4) — a tiny, explicit state machine.
STATE_INTAKE = "INTAKE"
STATE_CONFIRM = "CONFIRM"
STATE_GENERATING = "GENERATING"
STATE_COMPLETE = "COMPLETE"
STATE_REFUSED = "REFUSED"


class WorkflowSession(Base):
    """One guided run of a Workbench tool: intake → confirm → generate."""
    __tablename__ = "workflow_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    matter_id: Mapped[int | None] = mapped_column(Integer, index=True)      # optional Matter link

    workflow_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default=STATE_INTAKE, nullable=False)

    intake_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)       # answers so far
    assumptions_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # stated assumptions

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class WorkflowArtifact(Base):
    """The generated product: ordered sections + citations, versioned, review-gated."""
    __tablename__ = "workflow_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    session_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # [{"name": ..., "grounding": "FILE|LAW|BOTH|NONE", "content": ..., "blocked": bool}]
    content_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    citations_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), default="LOW", nullable=False)

    review_status: Mapped[str] = mapped_column(String(40), default=DRAFT_STATUS_REVIEW, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(Integer)
    approved_at: Mapped[DateTime | None] = mapped_column(DateTime)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class WorkbenchUpload(Base):
    """A scratch document upload for Workbench tools (WB-02 fills extraction in).

    `delete_after` implements the privacy promise: scratch uploads auto-delete
    (default 7 days) unless the advocate saves them to a Matter, at which point
    they become a versioned Document and leave this table's lifecycle."""
    __tablename__ = "workbench_uploads"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[int | None] = mapped_column(Integer, index=True)

    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_text_ref: Mapped[str | None] = mapped_column(String(300))   # path to extracted text
    anchors_ref: Mapped[str | None] = mapped_column(String(300))          # path to page/char anchors

    retention_policy: Mapped[str] = mapped_column(String(20), default="scratch_7d", nullable=False)
    delete_after: Mapped[DateTime | None] = mapped_column(DateTime, index=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
