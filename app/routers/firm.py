"""
Firm workspace & member management (Phase C).

A firm admin can invite members into THEIR tenant, set their role, and deactivate them.
Members share the tenant, so they automatically see the firm's tenant-scoped cases/diary.
Invited members set their own password via a reset link (we never choose it for them).

Guards: only firm_admin manages members; new members join the admin's tenant; a tenant can
never be left without an active firm_admin; a seat limit applies for the closed beta.
"""
import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.tenant import Tenant
from app.auth.dependencies import require_firm_admin, get_current_user
from app.auth.security import hash_password, create_reset_token
from app.services.email import send_email, email_enabled
from app.services.tenancy import write_audit
from app.schemas.firm import MemberOut, MemberInvite, MemberUpdate

router = APIRouter()

SEAT_LIMIT = 14   # closed-beta cap per firm


def _active_admins(db: Session, tenant_id: int, exclude_id: int | None = None):
    q = db.query(User).filter(User.tenant_id == tenant_id,
                              User.role == UserRole.firm_admin, User.is_active == True)
    if exclude_id:
        q = q.filter(User.id != exclude_id)
    return q.count()


def _owned_member(db: Session, member_id: int, tenant_id: int) -> User:
    m = db.get(User, member_id)
    if not m or m.tenant_id != tenant_id:
        raise HTTPException(404, "Member not found")
    return m


@router.get("/members", response_model=list[MemberOut])
def list_members(admin: User = Depends(require_firm_admin), db: Session = Depends(get_db)):
    return (db.query(User).filter(User.tenant_id == admin.tenant_id)
            .order_by(User.id).all())


@router.post("/members", status_code=201)
def invite_member(payload: MemberInvite, admin: User = Depends(require_firm_admin),
                  db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "A user with that email already exists.")
    active = db.query(User).filter(User.tenant_id == admin.tenant_id,
                                   User.is_active == True).count()
    if active >= SEAT_LIMIT:
        raise HTTPException(400, f"Seat limit reached ({SEAT_LIMIT}). Deactivate a member first.")

    member = User(
        tenant_id=admin.tenant_id, full_name=payload.full_name, email=payload.email,
        role=payload.role, is_verified=True, is_active=True,
        hashed_password=hash_password(secrets.token_urlsafe(24)),  # unusable until they reset
    )
    db.add(member); db.flush()

    token = create_reset_token(member.id, member.hashed_password)                 # invite = set-your-password link
    invite_link = f"/reset-password?token={token}"
    send_email(member.email, "You've been invited to Juriscite",
               f"{admin.full_name} added you to their firm workspace. "
               f"Set your password to get started:\n{invite_link}")
    write_audit(db, tenant_id=admin.tenant_id, user_id=admin.id,
                action="invite_member", entity="User", entity_id=member.id,
                detail=f"role={payload.role.value}")
    db.commit()

    resp = {"id": member.id, "email": member.email, "role": member.role.value,
            "status": "invited"}
    if not email_enabled():
        resp["dev_invite_token"] = token   # dev only; in prod the link is emailed
    return resp


@router.patch("/members/{member_id}", response_model=MemberOut)
def update_member(member_id: int, payload: MemberUpdate,
                  admin: User = Depends(require_firm_admin), db: Session = Depends(get_db)):
    member = _owned_member(db, member_id, admin.tenant_id)
    data = payload.model_dump(exclude_unset=True)

    # Never leave the tenant without an active admin.
    demoting = data.get("role") and data["role"] != UserRole.firm_admin
    deactivating = data.get("is_active") is False
    if (demoting or deactivating) and member.role == UserRole.firm_admin \
            and _active_admins(db, admin.tenant_id, exclude_id=member.id) == 0:
        raise HTTPException(400, "Cannot remove the last active firm admin.")

    if "role" in data:
        member.role = data["role"]
    if "is_active" in data:
        member.is_active = data["is_active"]
    db.commit(); db.refresh(member)
    write_audit(db, tenant_id=admin.tenant_id, user_id=admin.id,
                action="update_member", entity="User", entity_id=member.id)
    return member


@router.delete("/members/{member_id}", status_code=204)
def remove_member(member_id: int, admin: User = Depends(require_firm_admin),
                  db: Session = Depends(get_db)):
    member = _owned_member(db, member_id, admin.tenant_id)
    if member.id == admin.id:
        raise HTTPException(400, "You cannot remove yourself.")
    if member.role == UserRole.firm_admin and _active_admins(db, admin.tenant_id, exclude_id=member.id) == 0:
        raise HTTPException(400, "Cannot remove the last active firm admin.")
    member.is_active = False        # soft-deactivate (preserves audit trail + authored data)
    db.commit()
    write_audit(db, tenant_id=admin.tenant_id, user_id=admin.id,
                action="remove_member", entity="User", entity_id=member.id)


# ── Advocate/firm verification (LSAI-LEGAL-07) ───────────────────────────────────
class VerificationSubmit(BaseModel):
    jurisdiction: str | None = None
    bar_enrolment: str | None = None


def _ver_out(t: Tenant) -> dict:
    return {"status": t.verification_status, "jurisdiction": t.jurisdiction,
            "bar_enrolment": t.bar_enrolment, "note": t.verification_note,
            "verified_at": t.verified_at}


@router.get("/verification")
def get_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Current tenant's verification status (any member can view)."""
    t = db.get(Tenant, user.tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    return _ver_out(t)


@router.post("/verification")
def submit_verification(body: VerificationSubmit, admin: User = Depends(require_firm_admin),
                        db: Session = Depends(get_db)):
    """Firm admin submits enrolment/jurisdiction for founder review (status → pending)."""
    t = db.get(Tenant, admin.tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    if body.jurisdiction is not None:
        t.jurisdiction = body.jurisdiction.strip() or None
    if body.bar_enrolment is not None:
        t.bar_enrolment = body.bar_enrolment.strip() or None
    if t.verification_status != "verified":
        t.verification_status = "pending"
    db.commit()
    write_audit(db, tenant_id=admin.tenant_id, user_id=admin.id,
                action="verification_submit", entity="Tenant", entity_id=t.id)
    return _ver_out(t)
