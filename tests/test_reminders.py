"""
Phase A1 — reminder scheduler/engine tests.
Proves a due reminder actually fires, is idempotent, and surfaces in the feed.
"""
from datetime import date, timedelta
from tests.conftest import auth


def _admin(client, email="admin@firm.com"):
    r = client.post("/api/auth/register", json={
        "full_name": "Firm Admin", "email": email,
        "password": "Sup3rSecret!", "role": "firm_admin"})
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": "Sup3rSecret!"})
    return r.json()["access_token"]


def _case_with_hearing(client, tok, days_ahead=1):
    cid = client.post("/api/clients/", headers=auth(tok),
                      json={"full_name": "C", "email": "c@e.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(tok),
                          json={"title": "Sharma v. State", "client_id": cid, "status": "open"}).json()["id"]
    client.post("/api/diary/entries", headers=auth(tok), json={
        "case_id": case_id, "hearing_date": (date.today() + timedelta(days=days_ahead)).isoformat(),
        "court_name": "Delhi HC", "stage": "arguments"})
    return case_id


def test_due_reminder_fires_and_is_idempotent(client):
    tok = _admin(client)
    _case_with_hearing(client, tok, days_ahead=1)

    r1 = client.post("/api/notifications/run-reminders", headers=auth(tok))
    assert r1.status_code == 200
    assert r1.json()["fired"] >= 1

    r2 = client.post("/api/notifications/run-reminders", headers=auth(tok))
    assert r2.json()["fired"] == 0          # idempotent — no double-notify


def test_reminder_appears_in_feed_and_can_be_read(client):
    tok = _admin(client, "admin2@firm.com")
    _case_with_hearing(client, tok, days_ahead=1)
    client.post("/api/notifications/run-reminders", headers=auth(tok))

    feed = client.get("/api/notifications/", headers=auth(tok)).json()
    assert any("Hearing" in n["title"] for n in feed)
    assert client.get("/api/notifications/unread-count", headers=auth(tok)).json()["unread"] >= 1

    nid = feed[0]["id"]
    assert client.post(f"/api/notifications/{nid}/read", headers=auth(tok)).status_code == 204


def test_run_reminders_requires_admin(client):
    # plain advocate cannot trigger the scan
    from tests.conftest import register_and_login
    adv = register_and_login(client, "adv@firm.com")
    assert client.post("/api/notifications/run-reminders", headers=auth(adv)).status_code == 403


def test_notifications_require_auth(client):
    assert client.get("/api/notifications/").status_code == 401
