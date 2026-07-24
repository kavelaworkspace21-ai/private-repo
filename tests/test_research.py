"""
Legal-research (case-law) endpoint tests.
Auth-gate only — we do NOT call the live Indian Kanoon API in tests (cost + determinism).
"""
from tests.conftest import register_and_login, auth


def test_case_search_requires_auth(client):
    assert client.get("/api/research/cases?q=bail").status_code == 401


def test_case_summary_requires_auth(client):
    assert client.get("/api/research/cases/123/summary").status_code == 401


def test_status_requires_auth(client):
    assert client.get("/api/research/status").status_code == 401


def test_status_shape_when_authed(client):
    t = register_and_login(client, "research@firm.com")
    r = client.get("/api/research/status", headers=auth(t))
    assert r.status_code == 200
    assert "case_law_enabled" in r.json()


def test_provisions_requires_auth(client):
    assert client.get("/api/research/provisions?q=cheating").status_code == 401


def test_provisions_validation(client):
    t = register_and_login(client, "prov@firm.com")
    assert client.get("/api/research/provisions", headers=auth(t)).status_code == 422
    assert client.get("/api/research/provisions?q=a", headers=auth(t)).status_code == 422


def test_provisions_happy_path_shape(client):
    t = register_and_login(client, "prov2@firm.com")
    r = client.get("/api/research/provisions?q=cheating", headers=auth(t))
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)   # may be empty without the corpus (CI) — never an error
    for item in body[:3]:
        assert {"act", "section", "title"} <= set(item.keys())
