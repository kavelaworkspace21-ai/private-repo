import enum
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class CaseStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    closed = "closed"
    archived = "archived"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.open, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    client: Mapped["Client"] = relationship("Client", back_populates="cases")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    hearings: Mapped[list["Hearing"]] = relationship("Hearing", back_populates="case", cascade="all, delete-orphan")
    fees_collected: Mapped[list["FeeCollected"]] = relationship("FeeCollected", back_populates="case", cascade="all, delete-orphan")
    fees_due: Mapped[list["FeeDue"]] = relationship("FeeDue", back_populates="case", cascade="all, delete-orphan")
    diary_entries: Mapped[list["DiaryEntry"]] = relationship("DiaryEntry", back_populates="case", cascade="all, delete-orphan")
    diary_tasks: Mapped[list["DiaryTask"]] = relationship("DiaryTask", back_populates="case", cascade="all, delete-orphan")
    filing_deadlines: Mapped[list["FilingDeadline"]] = relationship("FilingDeadline", back_populates="case", cascade="all, delete-orphan")
    opposing_counsel: Mapped[list["OpposingCounsel"]] = relationship("OpposingCounsel", back_populates="case", cascade="all, delete-orphan")
