"""WB-07 (slice 1) — editor actions + review-own-draft endpoints.
No provider in CI: pinned here are the contracts — auth, validation, fail-closed 503,
and that a failed/blocked call never costs a plan unit. (Grounded output behaviour
follows the same gates as chat/workbench, exercised live.)"""
from tests.conftest import register_and_login, auth
from app.models.billing import KIND_RESEARCH


def test_edit_requires_auth_and_validates(client):
    assert client.post("/api/drafting/edit", json={"action": "expand", "selection": "x"}).status_code == 401
    t = register_and_login(client, "ed1@firm.com")
    r = client.post("/api/drafting/edit", headers=auth(t),
                    json={"action": "delete_everything", "selection": "some clause"})
    assert r.status_code == 422                                  # unknown action refused
    assert client.post("/api/drafting/edit", headers=auth(t),
                       json={"action": "expand", "selection": ""}).status_code == 422


def test_edit_fails_closed_without_model_key(client):
    t = register_and_login(client, "ed2@firm.com")
    r = client.post("/api/drafting/edit", headers=auth(t),
                    json={"action": "reword", "selection": "The party of the first part…"})
    assert r.status_code == 503                                  # no key → honest 503, no fake edit


def test_review_own_draft_contract(client):
    t = register_and_login(client, "ed3@firm.com")
    # too short to be a draft → 422
    assert client.post("/api/drafting/review-draft", headers=auth(t),
                       json={"content": "short"}).status_code == 422
    before = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    r = client.post("/api/drafting/review-draft", headers=auth(t),
                    json={"content": "IN THE COURT OF ... " * 20})
    assert r.status_code == 503                                  # no key → fail closed
    after = client.get("/api/billing/usage", headers=auth(t)).json()["items"][KIND_RESEARCH]["used"]
    assert after == before                                       # a failed review costs nothing


def test_review_over_quota_is_402_before_any_work(client):
    t = register_and_login(client, "ed4@firm.com")
    from app.main import app
    from app.db.session import get_db
    from app.models.user import User
    from app.services import billing as bl
    from app.models.billing import UsageEvent
    db = next(app.dependency_overrides[get_db]())
    try:
        tid = db.query(User).filter(User.email == "ed4@firm.com").first().tenant_id
        sub = bl.get_subscription(db, tid)
        sub.plan_code, sub.status, sub.trial_end = "free", "active", None
        uid = db.query(User).filter(User.email == "ed4@firm.com").first().id
        for _ in range(5):                                       # exhaust free tier
            db.add(UsageEvent(tenant_id=tid, user_id=uid, kind=KIND_RESEARCH))
        db.commit()
    finally:
        db.close()
    r = client.post("/api/drafting/review-draft", headers=auth(t),
                    json={"content": "IN THE COURT OF ... " * 20})
    assert r.status_code == 402
    assert r.json()["detail"]["upgrade_url"] == "/pricing"
