import os
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.auth.security import decode_token
from app.models.user import User, UserRole

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not credentials:
        raise exc
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise exc
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or getattr(user, "is_banned", False):
        raise exc            # banned = ejected from the ecosystem; every token is dead
    return user


def require_role(*roles: UserRole):
    def _dep(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return _dep


# Convenience deps
require_advocate   = require_role(UserRole.advocate, UserRole.firm_admin)
require_judge      = require_role(UserRole.judge)
require_firm_admin = require_role(UserRole.firm_admin)

# Roles permitted to create/update/delete matter data (RBAC — section 2). Clerks are
# read-only; citizen/judge/business are not matter managers in a firm workspace.
MATTER_WRITERS = (UserRole.advocate, UserRole.firm_admin, UserRole.associate)
require_matter_write = require_role(*MATTER_WRITERS)


def require_founder(x_admin_token: str | None = Header(default=None)) -> bool:
    """Founder/super-admin guard for cross-tenant actions (e.g. advocate verification).
    Uses the ADMIN_TOKEN env secret via the X-Admin-Token header. If ADMIN_TOKEN is unset,
    all such actions are denied (fail-closed). (LSAI-LEGAL-07)"""
    expected = os.getenv("ADMIN_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Founder admin token required")
    return True


def require_ai_consent(current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> User:
    """Consent gate at the AI boundary (DPDP Act 2023).

    Sending a matter to the model means client data leaves this system for a third-party
    LLM. That is exactly the processing consent exists to authorise, so it is enforced
    here rather than merely recorded. UNCONDITIONAL and fail-closed: there is no env flag
    to switch it off, because "consent enforcement, but disabled in production" is not
    consent.

    In practice this blocks firm-INVITED members who have never accepted — an admin
    created their account, so nothing was granted on their behalf. Self-registered users
    consent at registration and are unaffected. The 403 is actionable: accept at /consent.

    Compose it with require_ai_access (verification) via require_ai_user below.
    """
    from app.services.privacy import has_current_consent
    if not has_current_consent(db, current_user.id):
        raise HTTPException(
            status_code=403,
            detail="AI features need your consent to the current privacy policy. "
                   "Review and accept it at /consent, then try again.")
    return current_user


def require_ai_user(current_user: User = Depends(require_ai_consent),
                    db: Session = Depends(get_db)) -> User:
    """The full AI boundary: consent (always) + tenant verification (flag-gated).

    Every endpoint that sends tenant data to an LLM depends on THIS, so a new AI route
    cannot pick up one check and silently miss the other.
    """
    return require_ai_access(current_user, db)


def require_ai_access(current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> User:
    """AI access gate (LSAI-LEGAL-07). When AI_REQUIRES_VERIFICATION=1, AI legal research/drafting
    is restricted to verified advocate/firm tenants. Default OFF for the closed beta (founder
    approves manually); when enabled, unverified tenants get a clear 403."""
    if os.getenv("AI_REQUIRES_VERIFICATION", "0") == "1":
        from app.models.tenant import Tenant
        t = db.get(Tenant, current_user.tenant_id)
        if not t or getattr(t, "verification_status", "pending") != "verified":
            raise HTTPException(
                status_code=403,
                detail="AI features require a verified advocate/firm. Contact your administrator.")
    return current_user
