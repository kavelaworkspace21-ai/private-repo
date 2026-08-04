from sqlalchemy import Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.db.base import Base


class UserActivity(Base):
    __tablename__ = "user_activities"

    id: Mapped[int]              = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int]         = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type: Mapped[str]     = mapped_column(String(60), nullable=False, index=True)
    # e.g. "view_case", "create_hearing", "open_document", "draft_notice", "chat_query"
    entity_type: Mapped[str]     = mapped_column(String(60), nullable=True)
    # "case" | "client" | "hearing" | "document" | "diary_entry" | "conversation"
    entity_id: Mapped[int]       = mapped_column(Integer, nullable=True)
    entity_label: Mapped[str]    = mapped_column(String(300), nullable=True)
    # human-readable: e.g. "Sharma v. State of Maharashtra — IPC 420"
    meta: Mapped[dict]           = mapped_column(JSON, nullable=True)
    # extra structured data: {"court": "Bombay HC", "next_date": "2025-03-10"}
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), index=True)
