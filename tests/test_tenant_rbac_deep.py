"""
LSAI-LEGAL-13 — deep tenant-isolation + RBAC across every matter object type.
Cross-tenant access is a P0 bug; these must FAIL if isolation or the role gate breaks.
"""
from datetime import date
from tests.conftest import register_and_login, auth

TODAY = str(date.today())


def _seed_full(client, tok):
    cid = client.post("/api/clients/", headers=auth(tok),
                      json={"full_name": "R", "email": "r@e.com"}).json()["id"]
    case = client.post("/api/cases/", headers=auth(tok),
                       json={"title": "R v State", "client_id": cid, "status": "open"}).json()["id"]
    hid = client.post("/api/hearings/", headers=auth(tok),
                      json={"case_id": case, "hearing_date": TODAY, "court_name": "DC"}).json()["id"]
    fid = client.post("/api/fees/collected", headers=auth(tok),
                      json={"case_id": case, "amount": 1000, "payment_date": TODAY}).json()["id"]
    task = client.post("/api/diary/tasks", headers=auth(tok),
                       json={"case_id": case, "title": "file"}).json()["id"]
    did = client.post("/api/drafts/", headers=auth(tok),
                      json={"document_type": "legal_notice", "title": "N", "content": "body"}).json()["id"]
    return dict(cid=cid, case=case, hid=hid, fid=fid, task=task, did=did)


def test_cross_tenant_isolation_all_objects(client):
    t1 = register_and_login(client, "iso1@firm.com", "Iso One")
    t2 = register_and_login(client, "iso2@firm.com", "Iso Two")
    s = _seed_full(client, t1)

    # Reads denied (404 — no info leak)
    assert client.get(f"/api/hearings/{s['hid']}", headers=auth(t2)).status_code == 404
    assert client.get(f"/api/drafts/{s['did']}", headers=auth(t2)).status_code == 404

    # Lists are empty for the other tenant
    assert client.get("/api/hearings/", headers=auth(t2)).json() == []
    assert client.get("/api/fees/collected", headers=auth(t2)).json() == []
    assert client.get("/api/diary/tasks", headers=auth(t2)).json() == []
    assert client.get("/api/drafts/", headers=auth(t2)).json() == []

    # Mutations denied across every object type
    assert client.patch(f"/api/hearings/{s['hid']}", headers=auth(t2),
                        json={"court_name": "x"}).status_code == 404
    assert client.delete(f"/api/hearings/{s['hid']}", headers=auth(t2)).status_code == 404
    assert client.patch(f"/api/fees/collected/{s['fid']}", headers=auth(t2),
                        json={"amount": 5}).status_code == 404
    assert client.delete(f"/api/fees/collected/{s['fid']}", headers=auth(t2)).status_code == 404
    assert client.patch(f"/api/diary/tasks/{s['task']}", headers=auth(t2),
                        json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/diary/tasks/{s['task']}", headers=auth(t2)).status_code == 404
    assert client.patch(f"/api/drafts/{s['did']}", headers=auth(t2),
                        json={"content": "x"}).status_code == 404
    assert client.delete(f"/api/drafts/{s['did']}", headers=auth(t2)).status_code == 404
    assert client.post(f"/api/drafts/{s['did']}/approve", headers=auth(t2)).status_code == 404

    # The owner's data is untouched
    assert client.get(f"/api/hearings/{s['hid']}", headers=auth(t1)).status_code == 200


def test_cross_tenant_create_on_foreign_case_denied(client):
    t1 = register_and_login(client, "iso3@firm.com", "Iso3")
    t2 = register_and_login(client, "iso4@firm.com", "Iso4")
    case = _seed_full(client, t1)["case"]
    assert client.post("/api/hearings/", headers=auth(t2),
                       json={"case_id": case, "hearing_date": TODAY, "court_name": "DC"}).status_code == 404
    assert client.post("/api/fees/collected", headers=auth(t2),
                       json={"case_id": case, "amount": 1, "payment_date": TODAY}).status_code == 404
    assert client.post("/api/diary/tasks", headers=auth(t2),
                       json={"case_id": case, "title": "x"}).status_code == 404
    assert client.post("/api/drafts/", headers=auth(t2),
                       json={"document_type": "legal_notice", "title": "N",
                             "content": "b", "case_id": case}).status_code == 404


def _register_role(client, email, role):
    client.post("/api/auth/register", json={
        "full_name": "u", "email": email, "password": "Sup3rSecret!", "role": role})
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


def test_clerk_readonly_across_objects(client):
    clerk = _register_role(client, "clerk2@firm.com", "clerk")
    # Reads allowed
    assert client.get("/api/hearings/", headers=auth(clerk)).status_code == 200
    assert client.get("/api/drafts/", headers=auth(clerk)).status_code == 200
    # Writes forbidden (role gate fires before ownership)
    assert client.post("/api/hearings/", headers=auth(clerk),
                       json={"case_id": 1, "hearing_date": TODAY, "court_name": "DC"}).status_code == 403
    assert client.post("/api/fees/collected", headers=auth(clerk),
                       json={"case_id": 1, "amount": 1, "payment_date": TODAY}).status_code == 403
    assert client.post("/api/diary/tasks", headers=auth(clerk),
                       json={"case_id": 1, "title": "x"}).status_code == 403
    assert client.post("/api/drafts/", headers=auth(clerk),
                       json={"document_type": "legal_notice", "title": "N", "content": "b"}).status_code == 403
