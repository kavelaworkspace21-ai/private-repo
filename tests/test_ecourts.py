"""
eCourts + calendar tests. eCourts is read-only and disabled in tests (no base URL),
so we assert graceful 503 rather than calling any live API.
"""
from datetime import date
from tests.conftest import register_and_login, auth


def test_calendar_requires_auth(client):
    assert client.get("/api/calendar/diary.ics").status_code == 401


def test_calendar_ics_export(client):
    t = register_and_login(client, "cal@firm.com")
    # create a case + hearing so the calendar has content
    cid = client.post("/api/clients/", headers=auth(t),
                      json={"full_name": "C", "email": "c@e.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(t),
                          json={"title": "Cal v. Test", "client_id": cid, "status": "open"}).json()["id"]
    client.post("/api/diary/entries", headers=auth(t), json={
        "case_id": case_id, "hearing_date": date.today().isoformat(),
        "court_name": "Delhi HC", "stage": "arguments"})
    r = client.get("/api/calendar/diary.ics", headers=auth(t))
    assert r.status_code == 200
    assert "text/calendar" in r.headers["content-type"]
    assert "BEGIN:VCALENDAR" in r.text
    assert "Cal v. Test" in r.text


def test_ecourts_status(client):
    t = register_and_login(client, "ec@firm.com")
    r = client.get("/api/ecourts/status", headers=auth(t))
    assert r.status_code == 200
    assert "enabled" in r.json()


def test_ecourts_sync_disabled_returns_503(client):
    t = register_and_login(client, "ec2@firm.com")
    cid = client.post("/api/clients/", headers=auth(t),
                      json={"full_name": "D", "email": "d@e.com"}).json()["id"]
    case_id = client.post("/api/cases/", headers=auth(t),
                          json={"title": "X", "client_id": cid, "status": "open"}).json()["id"]
    r = client.post("/api/ecourts/sync", headers=auth(t),
                    json={"case_id": case_id, "cnr": "TEST123"})
    assert r.status_code == 503  # not configured (no ECOURTS_API_BASE)
