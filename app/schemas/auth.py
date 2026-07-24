from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from app.models.user import UserRole


class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str
    # Closed beta is advocate-first (CLAUDE.md §1): a registration that doesn't state a
    # role gets a working advocate workspace, not a locked-out citizen account.
    role: UserRole = UserRole.advocate
    phone: Optional[str] = None
    professional_id: Optional[str] = None  # Bar Council No., CIN, GSTIN etc.
    accept_terms: bool = True              # consent to terms + privacy (DPDP); decline => 400

    @field_validator("accept_terms")
    @classmethod
    def must_accept(cls, v):
        if v is False:
            raise ValueError("You must accept the Terms and Privacy Policy to register.")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class TOTPVerifyRequest(BaseModel):
    temp_token: str   # short-lived token issued after password check
    code: str         # 6-digit TOTP code from authenticator app


class TOTPEnableRequest(BaseModel):
    code: str         # user confirms setup by entering first code


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_2fa_setup: bool = False  # true when role needs 2FA but not yet set up


class TempTokenResponse(BaseModel):
    temp_token: str
    token_type: str = "bearer"
    message: str = "Enter your 2FA code to complete login"


class SetupTOTPResponse(BaseModel):
    secret: str
    qr_code_base64: str
    message: str


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str]
    role: UserRole
    is_verified: bool
    is_2fa_enabled: bool
    professional_id: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
