from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.tenancy import write_audit
from app.models.user import User, UserRole
from app.models.tenant import Tenant
from app.models.consent import ConsentRecord
from app.services.privacy import record_consents
from app.auth.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token, create_reset_token,
)
from app.services.email import send_email, email_enabled
from app.services.ratelimit import login_limiter, forgot_limiter, register_limiter
from app.auth.totp import generate_totp_secret, verify_totp_code, get_qr_code_base64
from app.auth.dependencies import get_current_user
from app.schemas.auth import (
    RegisterRequest, LoginRequest, TOTPVerifyRequest, TOTPEnableRequest,
    TokenResponse, TempTokenResponse, SetupTOTPResponse, UserOut, RefreshRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
)

router = APIRouter()

# ── Register ──────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=201,
             dependencies=[Depends(register_limiter)])
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")

    # Each registration creates its own tenant (firm/workspace). Members can later be
    # added to an existing tenant; for the closed beta, one advocate = one tenant.
    tenant = Tenant(name=f"{payload.full_name}'s Workspace")
    db.add(tenant)
    db.flush()  # get tenant.id before creating the user

    user = User(
        tenant_id=tenant.id,
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        phone=payload.phone,
        professional_id=payload.professional_id,
        is_verified=True,   # simplified: skip email OTP for now, mark verified
    )
    # Pre-generate TOTP secret for roles that will require 2FA
    if user.requires_2fa:
        user.totp_secret = generate_totp_secret()

    db.add(user)
    db.flush()

    # Record consent (DPDP Act): terms + privacy at current versions, with a provable receipt.
    record_consents(db, tenant_id=tenant.id, user_id=user.id,
                    source_ip=(request.client.host if request.client else None),
                    user_agent=request.headers.get("user-agent"),
                    acceptance_source="registration")

    db.commit()
    db.refresh(user)

    # 14-day Solo Advocate trial, no credit card (spec Part 2 `trial`; Part 4 forbids
    # forcing a card for a free trial). Expiry downgrades to Free — never auto-charges.
    from app.services.billing import start_trial
    start_trial(db, tenant.id)

    write_audit(db, tenant_id=tenant.id, user_id=user.id,
                action="register", entity="User", entity_id=user.id)
    return user


# ── Consents (DPDP — data principal can see their recorded consents) ──────────────

@router.get("/consents")
def my_consents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(ConsentRecord)
            .filter(ConsentRecord.user_id == current_user.id)
            .order_by(ConsentRecord.id.desc()).all())
    return [{"type": r.consent_type, "version": r.policy_version, "granted": r.granted,
             "at": r.created_at, "source": r.acceptance_source, "ip": r.source_ip}
            for r in rows]


@router.get("/needs-consent")
def needs_consent(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """True if the user has not granted consent at the CURRENT privacy version.
    Invited members (created by an admin) have none until they accept on first login."""
    from app.services.privacy import PRIVACY_VERSION, TERMS_VERSION, NOTICE_VERSION
    has = (db.query(ConsentRecord)
           .filter(ConsentRecord.user_id == current_user.id,
                   ConsentRecord.consent_type == "privacy_policy",
                   ConsentRecord.policy_version == PRIVACY_VERSION,
                   ConsentRecord.granted == True).first())
    return {"needs": has is None, "terms_version": TERMS_VERSION,
            "privacy_version": PRIVACY_VERSION, "notice_version": NOTICE_VERSION}


@router.post("/consent")
def give_consent(request: Request, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Record the current user's consent (terms + privacy) at the current versions."""
    record_consents(db, tenant_id=current_user.tenant_id, user_id=current_user.id,
                    source_ip=(request.client.host if request.client else None),
                    user_agent=request.headers.get("user-agent"),
                    acceptance_source="consent_page")
    db.commit()
    return {"status": "ok"}


# ── Login (step 1) ────────────────────────────────────────

@router.post("/login", dependencies=[Depends(login_limiter)])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if getattr(user, "is_banned", False):
        # Ejected from the ecosystem for a soul violation — final, no self-serve return.
        raise HTTPException(403, "Access permanently revoked.")
    if not user.is_active:
        raise HTTPException(403, "Account is disabled")

    # If role requires 2FA and it IS enabled → issue temp token, wait for TOTP
    if user.requires_2fa and user.is_2fa_enabled:
        temp = create_access_token(user.id, f"temp_{user.role}")
        return TempTokenResponse(
            temp_token=temp,
            message="Enter your 2FA code to complete login",
        )

    # If role requires 2FA but NOT yet set up → issue tokens + flag
    if user.requires_2fa and not user.is_2fa_enabled:
        write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                    action="login", entity="User", entity_id=user.id)
        return TokenResponse(
            access_token=create_access_token(user.id, user.role),
            refresh_token=create_refresh_token(user.id),
            requires_2fa_setup=True,
        )

    # Citizen: direct login
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="login", entity="User", entity_id=user.id)
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


# ── Login (step 2) — verify TOTP ─────────────────────────

@router.post("/login/verify-2fa", response_model=TokenResponse)
def verify_2fa_login(payload: TOTPVerifyRequest, db: Session = Depends(get_db)):
    decoded = decode_token(payload.temp_token)
    if not decoded or not decoded.get("role", "").startswith("temp_"):
        raise HTTPException(401, "Invalid or expired token")

    user = db.get(User, int(decoded["sub"]))
    if not user or not user.totp_secret:
        raise HTTPException(401, "User not found")

    if not verify_totp_code(user.totp_secret, payload.code):
        raise HTTPException(401, "Invalid 2FA code")

    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="login_2fa", entity="User", entity_id=user.id)
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


# ── 2FA Setup — get QR code ───────────────────────────────

@router.get("/2fa/setup", response_model=SetupTOTPResponse)
def setup_2fa(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.requires_2fa:
        raise HTTPException(400, "2FA is not required for your account role")
    if current_user.is_2fa_enabled:
        raise HTTPException(400, "2FA is already enabled")
    if not current_user.totp_secret:
        current_user.totp_secret = generate_totp_secret()
        db.commit()
        db.refresh(current_user)

    qr = get_qr_code_base64(current_user.totp_secret, current_user.email)
    return SetupTOTPResponse(
        secret=current_user.totp_secret,
        qr_code_base64=qr,
        message="Scan the QR code with your authenticator app, then confirm with a code.",
    )


# ── 2FA Setup — confirm and enable ───────────────────────

@router.post("/2fa/enable")
def enable_2fa(
    payload: TOTPEnableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.totp_secret:
        raise HTTPException(400, "Run /2fa/setup first")
    if not verify_totp_code(current_user.totp_secret, payload.code):
        raise HTTPException(401, "Invalid code — check your authenticator app and try again")

    current_user.is_2fa_enabled = True
    db.commit()
    write_audit(db, tenant_id=current_user.tenant_id, user_id=current_user.id,
                action="enable_2fa", entity="User", entity_id=current_user.id)
    return {"message": "2FA enabled successfully"}


# ── Refresh token ─────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(401, "Invalid or expired refresh token")
    user = db.get(User, int(decoded["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "User not found")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


# ── Forgot password ───────────────────────────────────────

@router.post("/forgot-password", dependencies=[Depends(forgot_limiter)])
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Always returns a generic message (never reveals whether an email is registered).
    If the user exists, a short-lived reset token is emailed. In dev (no SMTP configured)
    the token is returned as `dev_token` so the flow is usable/testable without email.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    generic = {"message": "If that email is registered, a password reset link has been sent."}
    if not user:
        return generic

    token = create_reset_token(user.id)
    reset_link = f"/reset-password?token={token}"
    send_email(
        user.email, "Reset your Juriscite password",
        f"Open this link to reset your password (valid 30 minutes):\n{reset_link}\n\n"
        f"If you did not request this, ignore this email.",
    )
    if not email_enabled():
        return {**generic, "dev_token": token}   # dev convenience only; never in prod (SMTP set)
    return generic


# ── Reset password ────────────────────────────────────────

@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    decoded = decode_token(payload.token)
    if not decoded or decoded.get("type") != "reset":
        raise HTTPException(400, "Invalid or expired reset link")
    user = db.get(User, int(decoded["sub"]))
    if not user or not user.is_active:
        raise HTTPException(400, "Invalid or expired reset link")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="password_reset", entity="User", entity_id=user.id)
    return {"message": "Password reset successful. You can now sign in."}


# ── Me ────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
