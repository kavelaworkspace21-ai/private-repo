"""
Entitlement enforcement (spec 3.4): quotas, 402 payloads, free-tier read-only diary,
and tenant-scoped metering.

These tests never reach the language model: an over-quota request is refused before any
model work, and the under-quota assertions are made against the service layer.
"""
import pytest

from tests.conftest import register_and_login, auth
from app.main import app
from app.db.session import get_db
from app.models.user import User
from app.models.billing import UsageEvent, KIND_RESEARCH, KIND_DRAFT
from app.services import billing as bl


def _db():
    """A Session bound to the same throwaway DB the TestClient is using."""
    return next(app.dependency_overrides[get_db]())


def _tenant_id(email: str) -> int:
    db = _db()
    try:
        return db.query(User).filter(User.email == email).first().tenant_id
    finally:
        db.close()


def _set_plan(email: str, plan_code: str):
    db = _db()
    try:
        sub = bl.get_subscription(db, _tenant_id(email))
        sub.plan_code = plan_code
        sub.status = "active"
        sub.trial_end = None
        db.commit()
    finally:
        db.close()


def _burn(email: str, kind: str, n: int):
    """Pre-fill usage so we can assert the boundary without n real AI calls."""
    db = _db()
    try:
        tid = _tenant_id(email)
        uid = db.query(User).filter(User.email == email).first().id
        for _ in range(n):
            db.add(UsageEvent(tenant_id=tid, user_id=uid, kind=kind))
        db.commit()
    finally:
        db.close()


# ── Quotas: free tier ─────────────────────────────────────────────────────────
def test_free_tier_blocks_the_sixth_research_query(client):
    email = "freeq@firm.com"
    t = register_and_login(client, email)
    _set_plan(email, "free")
    _burn(email, KIND_RESEARCH, 5)                     # the 5 the Free plan includes

    r = client.post("/api/ai/chat", headers=auth(t), json={"message": "What is Section 138 NI Act?"})
    assert r.status_code == 402
    d = r.json()["detail"]
    assert d["error"] == "limit_reached"
    assert d["kind"] == KIND_RESEARCH and d["used"] == 5 and d["limit"] == 5
    assert d["upgrade_url"] == "/pricing"
    assert "untouched" in d["message"]                 # honest, non-coercive copy


def test_free_tier_blocks_the_third_draft(client):
    email = "freed@firm.com"
    t = register_and_login(client, email)
    _set_plan(email, "free")
    _burn(email, KIND_DRAFT, 2)                        # the 2 the Free plan includes

    r = client.post("/api/drafting/generate", headers=auth(t),
                    json={"document_type": "affidavit", "fields": {"facts_to_state": "x"}})
    assert r.status_code == 402
    assert r.json()["detail"]["kind"] == KIND_DRAFT


def test_a_chat_draft_request_is_metered_as_a_draft_not_a_query(client):
    """Pricing promises '2 AI drafts / month' — a document drafted in chat is a draft."""
    email = "chatdraft@firm.com"
    t = register_and_login(client, email)
    _set_plan(email, "free")
    _burn(email, KIND_DRAFT, 2)                        # drafts exhausted, queries untouched

    r = client.post("/api/ai/chat", headers=auth(t),
                    json={"message": "Draft a legal notice for cheque bounce of Rs 2 lakh"})
    assert r.status_code == 402 and r.json()["detail"]["kind"] == KIND_DRAFT


# ── Quotas: paid tiers ────────────────────────────────────────────────────────
def test_solo_and_firm_allowances_come_from_plan_data(client):
    register_and_login(client, "solo@firm.com")
    db = _db()
    try:
        solo, firm = bl.get_plan(db, "solo_advocate"), bl.get_plan(db, "firm")
        assert bl.quota_for(solo, KIND_RESEARCH, seats=1) == 500
        assert bl.quota_for(solo, KIND_DRAFT, seats=1) == 150
        # firm is per-seat and pooled across the firm
        assert bl.quota_for(firm, KIND_RESEARCH, seats=3) == 1500
        assert bl.quota_for(firm, KIND_DRAFT, seats=5) == 750
        # enterprise is custom → unlimited (None), never a silent zero
        assert bl.quota_for(bl.get_plan(db, "enterprise"), KIND_RESEARCH, seats=10) is None
    finally:
        db.close()


def test_trial_user_is_under_quota_and_not_blocked(client):
    email = "trialq@firm.com"
    register_and_login(client, email)
    db = _db()
    try:
        bl.check_quota(db, _tenant_id(email), KIND_RESEARCH)   # must not raise
        bl.check_quota(db, _tenant_id(email), KIND_DRAFT)
    finally:
        db.close()


def test_usage_endpoint_reflects_recorded_usage(client):
    email = "usagecount@firm.com"
    t = register_and_login(client, email)
    _burn(email, KIND_RESEARCH, 3)
    u = client.get("/api/billing/usage", headers=auth(t)).json()
    assert u["items"][KIND_RESEARCH]["used"] == 3
    assert u["items"][KIND_RESEARCH]["remaining"] == 497


def test_expired_trial_falls_back_to_free_limits(client):
    """Entitlements never outlive the thing that paid for them."""
    from datetime import timedelta
    from app.util.time import utcnow
    email = "expired@firm.com"
    register_and_login(client, email)
    db = _db()
    try:
        sub = bl.get_subscription(db, _tenant_id(email))
        sub.trial_end = utcnow() - timedelta(days=1)
        db.commit()
        assert bl.effective_plan(db, sub).code == "free"
        assert bl.quota_for(bl.effective_plan(db, sub), KIND_RESEARCH, 1) == 5
    finally:
        db.close()


def test_usage_in_the_same_second_as_signup_is_counted(client):
    """Regression: usage_events.created_at must share the period window's clock and
    precision. A DB-side CURRENT_TIMESTAMP (second precision) sorted *before* a Python
    utcnow() period start, so a tenant's first-second usage vanished from the count."""
    email = "sameinstant@firm.com"
    register_and_login(client, email)
    db = _db()
    try:
        tid = _tenant_id(email)
        sub = bl.get_subscription(db, tid)
        # Force the worst case: period starts *after* the wall-clock second of the usage.
        sub.current_period_start = datetime_with_micros = sub.current_period_start.replace(microsecond=999_999)
        db.commit()
        uid = db.query(User).filter(User.email == email).first().id
        db.add(UsageEvent(tenant_id=tid, user_id=uid, kind=KIND_RESEARCH,
                          created_at=datetime_with_micros.replace(microsecond=0)))
        db.commit()
        assert bl.count_usage(db, tid, KIND_RESEARCH, sub.current_period_start) == 1
    finally:
        db.close()


# ── Metering is tenant-scoped ─────────────────────────────────────────────────
def test_usage_is_tenant_scoped(client):
    a, b = "meter_a@firm.com", "meter_b@firm.com"
    ta = register_and_login(client, a)
    tb = register_and_login(client, b)
    _burn(a, KIND_RESEARCH, 4)
    assert client.get("/api/billing/usage", headers=auth(ta)).json()["items"][KIND_RESEARCH]["used"] == 4
    assert client.get("/api/billing/usage", headers=auth(tb)).json()["items"][KIND_RESEARCH]["used"] == 0


# ── Free tier: court diary is read-only AT THE API, not just hidden in the UI ──
def test_free_tier_diary_is_read_only_at_the_api(client):
    email = "freediary@firm.com"
    t = register_and_login(client, email)
    cid = client.post("/api/clients/", headers=auth(t),
                      json={"full_name": "C", "email": "c@c.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(t),
                          json={"title": "C v. State", "client_id": cid, "status": "open"}).json()["id"]
    _set_plan(email, "free")

    # reads stay open
    assert client.get("/api/diary/tasks", headers=auth(t)).status_code == 200
    # every write is refused with an honest upgrade payload
    r = client.post("/api/diary/tasks", headers=auth(t),
                    json={"case_id": case_id, "title": "x", "due_date": "2026-08-01"})
    assert r.status_code == 402
    d = r.json()["detail"]
    assert d["error"] == "plan_upgrade_required" and d["feature"] == "court_diary"
    assert client.post("/api/hearings/", headers=auth(t),
                       json={"case_id": case_id, "hearing_date": "2026-08-01",
                             "court_name": "X"}).status_code == 402


def test_paid_tier_diary_is_writable(client):
    t = register_and_login(client, "paiddiary@firm.com")   # trial = solo = full diary
    cid = client.post("/api/clients/", headers=auth(t),
                      json={"full_name": "C", "email": "c2@c.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(t),
                          json={"title": "P v. State", "client_id": cid, "status": "open"}).json()["id"]
    r = client.post("/api/diary/tasks", headers=auth(t),
                    json={"case_id": case_id, "title": "ok", "due_date": "2026-08-01"})
    assert r.status_code == 201
