import enum
from sqlalchemy import String, Boolean, DateTime, Integer, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.db.crypto import EncryptedString


class UserRole(str, enum.Enum):
    citizen    = "citizen"
    advocate   = "advocate"
    judge      = "judge"
    firm_admin = "firm_admin"
    business   = "business"
    associate  = "associate"   # junior advocate — can manage matters
    clerk      = "clerk"       # support staff — read-only on matter data


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.citizen, nullable=False)

    # Email verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 2FA (mandatory for advocate / judge / firm_admin / business).
    # Stored encrypted at rest (Fernet) — widened to hold ciphertext. See app/db/crypto.py.
    totp_secret: Mapped[str | None] = mapped_column(EncryptedString(255))
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Role-specific ID (Bar Council No. / CIN / GSTIN etc.)
    professional_id: Mapped[str | None] = mapped_column(String(100))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Soul-violation ejection (owner directive 2026-06-24): a user who attempts to misuse Juriscite
    # against the law / against the soul is ejected from the ecosystem — banned and barred from auth.
    # There is intentionally NO self-serve un-ban path ("forever"); reversal is a manual owner action.
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    banned_reason: Mapped[str | None] = mapped_column(String(200))
    banned_at: Mapped[DateTime | None] = mapped_column(DateTime)

    # Revocation epoch. Any token whose `iat` predates this is refused. Bumped on password
    # reset and on "sign out everywhere" — the only way to kill an already-issued stateless
    # JWT without keeping a blacklist of every token ever minted.
    tokens_valid_from: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    @property
    def requires_2fa(self) -> bool:
        return self.role in (UserRole.advocate, UserRole.judge, UserRole.firm_admin, UserRole.business)
