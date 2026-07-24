from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from app.models.user import UserRole

# Roles a firm admin may assign to members of their workspace.
FIRM_ROLES = {UserRole.advocate, UserRole.associate, UserRole.clerk, UserRole.firm_admin}


class MemberOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    is_2fa_enabled: bool
    created_at: Optional[datetime]
    model_config = {"from_attributes": True}


class MemberInvite(BaseModel):
    full_name: str
    email: str
    role: UserRole = UserRole.associate

    @field_validator("role")
    @classmethod
    def role_allowed(cls, v):
        if v not in FIRM_ROLES:
            raise ValueError("Role must be advocate, associate, clerk, or firm_admin.")
        return v


class MemberUpdate(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def role_allowed(cls, v):
        if v is not None and v not in FIRM_ROLES:
            raise ValueError("Role must be advocate, associate, clerk, or firm_admin.")
        return v
