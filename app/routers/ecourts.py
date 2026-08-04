"""
eCourts + calendar integration (read-only eCourts, per CLAUDE.md authorized 2026-06-19).

- GET  /api/calendar/diary.ics     → download the Court Diary as an .ics (any calendar app)
- GET  /api/ecourts/status         → is the eCourts API configured?
- GET  /api/ecourts/case/{cnr}     → preview hearings for a CNR (read-only, no DB write)
- POST /api/ecourts/sync           → mirror eCourts hearings into the Court Diary (write)
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.diary_entry import DiaryEntry, HearingStage, HearingOutcome
from app.auth.dependencies import get_current_user, require_matter_write
from app.services.tenancy import current_tenant_id, get_owned_case, write_audit
from app.services.calendar_export import build_diary_ics
from app.integrations import ecourts

router = APIRouter()


# ── Calendar export (.ics) ──────────────────────────────────────────────────────
@router.get("/calendar/diary.ics")
def diary_ics(db: Session = Depends(get_db), tenant_id: int = Depends(current_tenant_id)):
    ics = build_diary_ics(db, tenant_id)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="court_diary.ics"'},
    )


# ── eCourts (read-only) ─────────────────────────────────────────────────────────
@router.get("/ecourts/status")
def ecourts_status(_: User = Depends(get_current_user)):
    return ecourts.status()


@router.get("/ecourts/case/{cnr}")
def ecourts_preview(cnr: str, _: User = Depends(get_current_user)):
    if not ecourts.is_enabled():
        raise HTTPException(503, "eCourts API not configured (set ECOURTS_API_BASE).")
    hearings = ecourts.fetch_hearings(cnr.strip())
    return {"cnr": cnr, "count": len(hearings),
            "hearings": [{**h, "date": h["date"].isoformat()} for h in hearings]}


class SyncRequest(BaseModel):
    case_id: int
    cnr: str


@router.post("/ecourts/sync")
def ecourts_sync(body: SyncRequest, db: Session = Depends(get_db),
                 user: User = Depends(require_matter_write)):
    """Pull eCourts hearings for a CNR into the Court Diary for an owned case."""
    if not ecourts.is_enabled():
        raise HTTPException(503, "eCourts API not configured (set ECOURTS_API_BASE).")
    case = get_owned_case(body.case_id, user.tenant_id, db)   # tenant ownership check

    hearings = ecourts.fetch_hearings(body.cnr.strip())
    if not hearings:
        return {"status": "no_data", "imported": 0,
                "message": "No hearings returned for that CNR."}

    existing = {
        (e.hearing_date, e.court_name)
        for e in db.query(DiaryEntry).filter(DiaryEntry.case_id == case.id).all()
    }
    imported = 0
    for h in hearings:
        key = (h["date"], h["court"] or "")
        if key in existing:
            continue                       # idempotent — don't duplicate
        db.add(DiaryEntry(
            case_id=case.id, tenant_id=user.tenant_id,
            hearing_date=h["date"], court_name=h["court"] or "eCourts",
            stage=HearingStage.other, outcome=HearingOutcome.pending,
            order_notes=f"Imported from eCourts (CNR {body.cnr}) — {h['purpose']}",
        ))
        imported += 1
    db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="ecourts_sync", entity="Case", entity_id=case.id,
                detail=f"CNR {body.cnr}: {imported} hearings")
    return {"status": "ok", "imported": imported, "total_found": len(hearings)}
