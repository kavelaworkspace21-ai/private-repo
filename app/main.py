import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.version import __version__
from app.auth.dependencies import require_firm_admin
from app.db.session import get_db

from app.routers import (
    clients, cases, documents, hearings, fees,
    diary, diary_summary, auth, ai_chat, ai_drafting, drafts, research, library, ecourts,
    notifications, account, audit, firm, data_rights, misuse, billing, workbench,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: disk preflight + background scheduler. Both helpers are defined further down;
    # Python resolves the names at call time (the module is fully imported before startup), so
    # this stays close to the FastAPI() call while the implementations live with their comments.
    _disk_preflight()
    _start_reminder_scheduler()
    try:
        yield
    finally:
        # Clean shutdown so the scheduler thread doesn't outlive the app (esp. under reload).
        sched = getattr(app.state, "scheduler", None)
        if sched is not None:
            try:
                sched.shutdown(wait=False)
            except Exception:
                pass


app = FastAPI(
    title="Juriscite",
    description="India's Legal Operating System",
    version=__version__,
    lifespan=lifespan,
)

# Legal guardrail (LSAI-LEGAL-09): prohibited AI features must never be enabled.
from app.legal_config import assert_prohibited_disabled, identity_summary
assert_prohibited_disabled()

# THE SOUL (hard-wired, fail-closed): the app REFUSES TO BOOT if the safety doctrine is broken,
# disabled, or tampered with. See app/soul.py + docs/governance/SOUL_HARDWIRED_CONSTITUTION.md.
from app.soul import assert_soul_intact
assert_soul_intact()

# Secret sanity (fail-closed): refuse to boot in production with a missing/placeholder
# JWT_SECRET or an unset FIELD_ENCRYPTION_KEY. preflight() already blocks a DEPLOY without
# these, but nothing stopped a hand-started uvicorn from running with the published
# placeholder and issuing forgeable tokens. This is the gate that always runs.
from app.security_gate import assert_secrets_sane
assert_secrets_sane()

# Observability (production discipline): request IDs always; Sentry only if SENTRY_DSN is set.
from app.observability import configure_logging, init_sentry, RequestIDMiddleware
configure_logging()
init_sentry()
app.add_middleware(RequestIDMiddleware)

# ── Activity tracking middleware ───────────────────────────────────────────────
@app.middleware("http")
async def activity_middleware(request: Request, call_next):
    """
    Passively log page views and key API calls for activity context.
    Only tracks authenticated GET requests to page routes and key POST APIs.
    """
    response = await call_next(request)

    # Only log successful, authenticated API calls worth tracking
    if response.status_code in (200, 201) and request.method in ("GET", "POST"):
        path = request.url.path
        # Map paths to action types
        action = None
        if path.startswith("/api/cases") and request.method == "GET":
            action = "view_case"
        elif path.startswith("/api/clients") and request.method == "GET":
            action = "view_client"
        elif path.startswith("/api/hearings") and request.method == "POST":
            action = "create_hearing"
        elif path.startswith("/api/diary") and request.method == "POST":
            action = "create_diary"
        elif path.startswith("/api/documents") and request.method == "POST":
            action = "upload_document"
        elif path.startswith("/api/drafting/generate") and request.method == "POST":
            action = "draft_document"
        # Actual chat logging is done inside ai_chat.py — skip here to avoid duplication
        if action:
            try:
                from app.db.session import SessionLocal
                from app.auth.security import decode_token
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token:
                    payload = decode_token(token)
                    user_id = payload.get("sub")
                    if user_id:
                        db = SessionLocal()
                        try:
                            from app.ai.activity_tracker import log_activity
                            log_activity(db, int(user_id), action,
                                         meta={"path": path, "method": request.method})
                        finally:
                            db.close()
            except Exception:
                pass  # Never let middleware crash the request

    return response


# ── Security headers (Phase B hardening) ────────────────────────────────────────
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "   # current frontend uses inline handlers + /static js
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "                # 2FA QR codes are data: URIs
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "no-referrer")
    h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # HSTS is honoured only over HTTPS; harmless to send over HTTP.
    h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    # Skip the strict CSP on the API docs (Swagger/Redoc load assets from a CDN).
    if not request.url.path.startswith(_DOCS_PATHS):
        h.setdefault("Content-Security-Policy", _CSP)
    return response


# ── API Routes ─────────────────────────────────────────────────────────────────
app.include_router(auth.router,             prefix="/api/auth",      tags=["Auth"])
app.include_router(clients.router,          prefix="/api/clients",   tags=["Clients"])
app.include_router(cases.router,            prefix="/api/cases",     tags=["Cases"])
app.include_router(documents.router,        prefix="/api/documents", tags=["Documents"])
app.include_router(hearings.router,         prefix="/api/hearings",  tags=["Hearings"])
app.include_router(fees.router,             prefix="/api/fees",      tags=["Fees"])
app.include_router(diary.router,            prefix="/api/diary",     tags=["Court Diary"])
app.include_router(diary_summary.router,    prefix="/api/diary",     tags=["Court Diary Summary"])
app.include_router(ai_chat.router,          prefix="/api/ai",        tags=["AI Legal Assistant"])
app.include_router(ai_drafting.router,      prefix="/api/drafting",  tags=["AI Drafting Engine"])
app.include_router(drafts.router,           prefix="/api/drafts",    tags=["Saved Drafts"])
app.include_router(research.router,         prefix="/api/research",  tags=["Legal Research"])
app.include_router(library.router,          prefix="/api/library",   tags=["Legal Library"])
app.include_router(ecourts.router,          prefix="/api",           tags=["eCourts & Calendar"])
app.include_router(notifications.router,     prefix="/api/notifications", tags=["Notifications"])
app.include_router(account.router,           prefix="/api/account",   tags=["Account & Data Rights"])
app.include_router(data_rights.router,        prefix="/api/data-rights", tags=["Data Rights Requests"])
app.include_router(misuse.router,             prefix="/api/misuse",    tags=["Misuse Reports"])
app.include_router(audit.router,             prefix="/api/audit",     tags=["Audit Log"])
app.include_router(firm.router,              prefix="/api/firm",      tags=["Firm Workspace"])
app.include_router(billing.router,           prefix="/api/billing",   tags=["Billing & Subscriptions"])
app.include_router(workbench.router,         prefix="/api/workbench", tags=["Advocate Workbench"])


# ── Disk preflight (S0.2) — surface a near-full store volume at boot ────────────
# (invoked from the lifespan handler above)
def _disk_preflight():
    """Log free space on the volume backing the vector store; warn when it runs low.

    The 2026-07-20 incident (C: at 43 MB free → sqlite 'disk full' corrupted a reseed)
    was invisible until it failed. This makes low disk loud at startup; reseed itself
    now refuses below a hard floor (see vector_store.reseed)."""
    import logging
    log = logging.getLogger(__name__)
    try:
        from app.ai.vector_store import disk_free_bytes, DISK_WARN_FREE_BYTES, CHROMA_PATH
        free = disk_free_bytes()
        gb = free / 1024 ** 3
        if free < DISK_WARN_FREE_BYTES:
            log.warning(
                f"Disk preflight: only {gb:.2f} GB free on the vector-store volume "
                f"({CHROMA_PATH}). Reseeds and backups may fail — free space soon.")
        else:
            log.info(f"Disk preflight: {gb:.2f} GB free on the vector-store volume.")
    except Exception as e:
        log.warning(f"Disk preflight could not run: {e}")


# ── Reminder scheduler (Phase A1) — fires due hearing/deadline reminders daily ──
# (invoked from the lifespan handler above)
def _start_reminder_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.db.session import get_db
        from app.services.notifications import run_due_reminders
        from app.services.scheduler import run_tracked_job
        from app.util.time import utcnow

        def _daily_slot():
            return utcnow().strftime("%Y-%m-%d")

        # Job bodies take the db and RETURN a short detail string (persisted on the job run).
        def _reminders_body(db):
            fired = run_due_reminders(db)
            from app.services.privacy import purge_old_read_notifications
            purged = purge_old_read_notifications(db)   # conservative retention
            # WB-02 privacy promise: scratch Workbench uploads auto-delete after 7 days.
            from app.services.workbench.uploads import purge_expired
            wb_purged = purge_expired(db)
            return f"{fired} reminders fired, {purged} notifications purged, {wb_purged} uploads deleted"

        def _backup_body(db):
            from app.services.backup import run_backup
            run = run_backup(db, trigger="scheduled")
            return getattr(run, "status", "done")

        def _drift_body(db):
            # Roadmap P3: weekly drift check against the OFFICIAL India Code bitstreams.
            # Reports only (never auto-ingests — re-ingestion is a human-supervised slice).
            from app.ai.corpus_updates import check_upstream
            s = check_upstream()["summary"]
            return (f"{s['checked']} checked, {s['updated_upstream']} changed upstream, "
                    f"{s['errors']} errors, {s.get('unverified_currency', 0)} unverified")

        # Each job is tracked + idempotent per slot (see app/services/scheduler.py).
        def _reminders_job(slot=None):
            db = next(get_db())
            try:
                run_tracked_job(db, "daily_reminders", slot or _daily_slot(), _reminders_body)
            finally:
                db.close()

        def _startup_reminders_job():
            # unique slot per boot → always runs on startup (not deduped against the daily slot)
            _reminders_job(slot=f"boot-{utcnow().strftime('%Y%m%dT%H%M%S')}")

        def _backup_job():
            db = next(get_db())
            try:
                run_tracked_job(db, "daily_backup", _daily_slot(), _backup_body)
            finally:
                db.close()

        def _corpus_freshness_job():
            db = next(get_db())
            try:
                run_tracked_job(db, "weekly_corpus_freshness", utcnow().strftime("%G-W%V"), _drift_body)
            finally:
                db.close()

        sched = BackgroundScheduler(daemon=True)
        sched.add_job(_reminders_job, "cron", hour=7, minute=0, id="daily_reminders",
                      replace_existing=True)          # 07:00 daily
        sched.add_job(_startup_reminders_job, "date", id="startup_reminders",
                      replace_existing=True)          # once on boot
        sched.add_job(_backup_job, "cron", hour=2, minute=0, id="daily_backup",
                      replace_existing=True)          # 02:00 daily DB backup (cron-only)
        sched.add_job(_corpus_freshness_job, "cron", day_of_week="mon", hour=3, minute=0,
                      id="weekly_corpus_freshness", replace_existing=True)  # Mon 03:00
        sched.start()
        app.state.scheduler = sched
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Reminder scheduler not started: {e}")


# ── Admin: reseed corpus ───────────────────────────────────────────────────────
@app.post("/api/admin/reseed-corpus", tags=["Admin"], include_in_schema=True)
def reseed_corpus(_admin=Depends(require_firm_admin)):
    """Force re-embed the legal corpus into ChromaDB (run after updating the corpus)."""
    try:
        from app.ai.vector_store import reseed
        col = reseed()
        return {"status": "ok", "sections_indexed": col.count()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/api/admin/ingest-statutes", tags=["Admin"], include_in_schema=True)
def ingest_statutes_endpoint(_admin=Depends(require_firm_admin)):
    """
    Parse every official Act PDF present in data/source_pdfs/ into verified full text,
    then re-embed. Run AFTER placing the official India Code PDFs in that folder.
    """
    try:
        from app.ai.ingest_statutes import STATUTE_REGISTRY, ingest, PDF_DIR
        from app.ai.vector_store import reseed
        results = []
        for aid in STATUTE_REGISTRY:
            if (PDF_DIR / f"{aid}.pdf").exists():
                try:
                    results.append(ingest(aid))
                except Exception as e:
                    results.append({"act_id": aid, "error": str(e)})
        col = reseed()
        return {"status": "ok", "ingested": results, "sections_indexed": col.count()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ── Admin: database backups (Phase B — data protection) ────────────────────────
def _serialize_backup(b):
    return {
        "id": b.id, "engine": b.engine, "status": b.status, "trigger": b.trigger,
        "location": b.location, "size_bytes": b.size_bytes, "detail": b.detail,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "finished_at": b.finished_at.isoformat() if b.finished_at else None,
    }


@app.post("/api/admin/backup", tags=["Admin"])
def trigger_backup(admin=Depends(require_firm_admin), db: Session = Depends(get_db)):
    """Run a database backup now (firm admin). Returns the recorded BackupRun (metadata only)."""
    from app.services.backup import run_backup
    run = run_backup(db, trigger="manual", user=admin)
    return _serialize_backup(run)


@app.get("/api/admin/backups", tags=["Admin"])
def list_backups(admin=Depends(require_firm_admin), db: Session = Depends(get_db)):
    """List recent backup runs (firm admin)."""
    from app.models.backup_run import BackupRun
    rows = db.query(BackupRun).order_by(BackupRun.id.desc()).limit(50).all()
    return [_serialize_backup(b) for b in rows]


# ── Founder: advocate/firm verification (LSAI-LEGAL-07) ─────────────────────────
from app.auth.dependencies import require_founder
from pydantic import BaseModel as _BaseModel


class _VerifyDecision(_BaseModel):
    status: str          # "verified" | "rejected" | "pending"
    note: str | None = None


@app.get("/api/admin/pending-verifications", tags=["Admin"])
def pending_verifications(_f=Depends(require_founder), db: Session = Depends(get_db)):
    """Founder-only: tenants awaiting verification (X-Admin-Token)."""
    from app.models.tenant import Tenant
    rows = (db.query(Tenant).filter(Tenant.verification_status != "verified")
            .order_by(Tenant.id).all())
    return [{"tenant_id": t.id, "name": t.name, "status": t.verification_status,
             "jurisdiction": t.jurisdiction, "bar_enrolment": t.bar_enrolment} for t in rows]


@app.patch("/api/admin/verify/{tenant_id}", tags=["Admin"])
def decide_verification(tenant_id: int, body: _VerifyDecision,
                        _f=Depends(require_founder), db: Session = Depends(get_db)):
    """Founder-only: approve/reject a tenant's advocate verification (X-Admin-Token)."""
    from datetime import datetime, timezone
    from app.models.tenant import Tenant
    from app.models.audit import AuditLog
    if body.status not in ("verified", "rejected", "pending"):
        raise HTTPException(422, "status must be verified|rejected|pending")
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    t.verification_status = body.status
    t.verification_note = (body.note or None)
    t.verified_at = datetime.now(timezone.utc) if body.status == "verified" else None
    db.add(AuditLog(tenant_id=t.id, user_id=0, action="verification_decision",
                    entity="Tenant", entity_id=t.id, detail=f"founder:{body.status}"))
    db.commit()
    return {"tenant_id": t.id, "status": t.verification_status, "verified_at": t.verified_at}


# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ── PWA: installable web app (Android "Install app" + iOS "Add to Home Screen") ──
# Served at ROOT scope so the service worker can control the whole origin.
@app.get("/manifest.webmanifest", include_in_schema=False)
def pwa_manifest():
    return FileResponse("app/static/manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
def pwa_service_worker():
    return FileResponse(
        "app/static/service-worker.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/offline", include_in_schema=False)
def pwa_offline():
    return FileResponse("app/static/offline.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Browsers request /favicon.ico by default; serve the SVG mark (404 noise otherwise).
    return FileResponse("app/static/favicon.svg", media_type="image/svg+xml")


# ── Frontend pages ─────────────────────────────────────────────────────────────
@app.get("/",            include_in_schema=False)
def index():             return FileResponse("app/templates/index.html")

@app.get("/cases",       include_in_schema=False)
def cases_page():        return FileResponse("app/templates/cases.html")

@app.get("/diary",       include_in_schema=False)
def diary_page():        return FileResponse("app/templates/diary.html")

@app.get("/login",       include_in_schema=False)
def login_page():        return FileResponse("app/templates/login.html")

@app.get("/register",    include_in_schema=False)
def register_page():     return FileResponse("app/templates/register.html")

@app.get("/setup-2fa",   include_in_schema=False)
def setup_2fa_page():    return FileResponse("app/templates/setup_2fa.html")

@app.get("/reset-password", include_in_schema=False)
def reset_password_page(): return FileResponse("app/templates/reset.html")

@app.get("/consent",     include_in_schema=False)
def consent_page():      return FileResponse("app/templates/consent.html")

@app.get("/assistant",   include_in_schema=False)
def assistant_page():    return FileResponse("app/templates/assistant.html")

@app.get("/drafting",    include_in_schema=False)
def drafting_page():     return FileResponse("app/templates/drafting.html")

@app.get("/workbench",   include_in_schema=False)
def workbench_page():   return FileResponse("app/templates/workbench.html")

@app.get("/drafts",      include_in_schema=False)
def drafts_page():       return FileResponse("app/templates/drafts.html")

@app.get("/library",     include_in_schema=False)
def library_page():      return FileResponse("app/templates/library.html")

@app.get("/firm",        include_in_schema=False)
def firm_page():         return FileResponse("app/templates/firm.html")

@app.get("/account",     include_in_schema=False)
def account_page():      return FileResponse("app/templates/account.html")

@app.get("/notifications", include_in_schema=False)
def notifications_page(): return FileResponse("app/templates/notifications.html")

@app.get("/pricing", include_in_schema=False)
def pricing_page():       return FileResponse("app/templates/pricing.html")

@app.get("/legal", include_in_schema=False)
def legal_hub_page():     return FileResponse("app/templates/legal.html")

@app.get("/legal/{slug}", include_in_schema=False)
def legal_doc_page(slug: str): return FileResponse("app/templates/legal.html")


# ── Legal: product identity + policy pack (public; LSAI-LEGAL-01 / 02) ───────────
@app.get("/api/legal/identity", tags=["Legal"])
def legal_identity():
    """Public product-identity + guardrail summary (advocate-only; no prohibited features)."""
    return identity_summary()


LEGAL_DOCS = {
    "terms":           ("Terms of Service",              "TERMS_OF_SERVICE.md"),
    "privacy":         ("Privacy Policy",                "PRIVACY_POLICY.md"),
    "acceptable-use":  ("Acceptable Use Policy",         "ACCEPTABLE_USE_POLICY.md"),
    "grievance":       ("Grievance Redressal Policy",    "GRIEVANCE_POLICY.md"),
    "ai-disclosure":   ("AI Use & Disclosure Policy",    "AI_USE_DISCLOSURE_POLICY.md"),
    "retention":       ("Data Retention Policy",         "RETENTION_POLICY.md"),
    "subprocessors":   ("Subprocessor Register",         "SUBPROCESSOR_REGISTER.md"),
    "law-enforcement": ("Law-Enforcement Request Policy", "LAW_ENFORCEMENT_REQUEST_POLICY.md"),
}


@app.get("/api/legal/index", tags=["Legal"])
def legal_index():
    return [{"slug": s, "title": t} for s, (t, _) in LEGAL_DOCS.items()]


@app.get("/api/legal/doc/{slug}", tags=["Legal"])
def legal_doc(slug: str):
    meta = LEGAL_DOCS.get(slug)
    if not meta:
        raise HTTPException(404, "Unknown policy")
    title, fn = meta
    try:
        with open(os.path.join("docs", "legal", fn), encoding="utf-8") as f:
            md = f.read()
    except FileNotFoundError:
        raise HTTPException(404, "Policy file missing")
    return {"slug": slug, "title": title, "markdown": md}


# ── Health & readiness ──────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    # If the app is serving at all, the soul passed the startup guard; re-check live for honesty.
    from app.soul import check_soul
    return {"status": "ok", "version": __version__,
            "soul": "intact" if not check_soul() else "VIOLATION"}


@app.get("/healthz", tags=["System"])
def healthz(db: Session = Depends(get_db)):
    """Liveness: process up, soul intact, DB answers. Cheap — no model/corpus network.
    Returns 503 so a load balancer pulls the instance if the soul is broken or the DB is down."""
    from sqlalchemy import text
    from app.soul import check_soul
    soul_ok = not check_soul()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    ok = soul_ok and db_ok
    return JSONResponse(
        {"status": "ok" if ok else "unhealthy", "version": __version__,
         "soul": "intact" if soul_ok else "VIOLATION", "db": "ok" if db_ok else "down"},
        status_code=200 if ok else 503)


@app.get("/readyz", tags=["System"])
def readyz():
    """Readiness: soul intact AND the vector index is built (chunks > 0). Returns 503 (AI not
    ready) otherwise — WITHOUT a fresh model probe and WITHOUT ever triggering a reseed."""
    from app.soul import check_soul
    from app.ops.release import _chroma_count, _embedding_model, load_release
    soul_ok = not check_soul()
    count = _chroma_count()
    index_ok = count is not None and count > 0
    ready = soul_ok and index_ok
    rel = load_release()
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "version": __version__,
         "soul": "intact" if soul_ok else "VIOLATION",
         "vector_index": {"chunks": count, "expected": rel.get("expected_chunk_count"), "ok": index_ok},
         "embedding_model": _embedding_model()},
        status_code=200 if ready else 503)


@app.get("/api/admin/status", tags=["Admin"])
def ops_status(_admin=Depends(require_firm_admin)):
    """Protected operational status (Phase 1 §5): app version, migration head, corpus fingerprint,
    vector-index count, model-config name, and config-PRESENCE booleans — never secret values."""
    from app.ops.release import live_status
    return live_status()
