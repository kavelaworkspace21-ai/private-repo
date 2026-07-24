from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class OpposingCounsel(Base):
    __tablename__ = "opposing_counsel"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    advocate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bar_registration_number: Mapped[str | None] = mapped_column(String(100))
    firm_name: Mapped[str | None] = mapped_column(String(200))
    contact: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="opposing_counsel")
