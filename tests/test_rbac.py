"""
RBAC tests (CLAUDE.md section 2 / 9): each role can do only what it should.
Clerks are read-only on matter data; advocates can write.
"""
from tests.conftest import auth


def _register(client, email, role):
    r = client.post("/api/auth/register", json={
        "full_name": f"{role} user", "email": email,
        "password": "Sup3rSecret!", "role": role,
    })
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": "Sup3rSecret!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_clerk_can_read_but_not_write(client):
    clerk = _register(client, "clerk@firm.com", "clerk")
    # read is allowed
    assert client.get("/api/clients/", headers=auth(clerk)).status_code == 200
    # write is forbidden
    r = client.post("/api/clients/", headers=auth(clerk),
                    json={"full_name": "X", "email": "x@e.com"})
    assert r.status_code == 403, r.text


def test_advocate_can_write(client):
    adv = _register(client, "adv@firm.com", "advocate")
    r = client.post("/api/clients/", headers=auth(adv),
                    json={"full_name": "Y", "email": "y@e.com"})
    assert r.status_code == 201, r.text


def test_associate_can_write(client):
    asc = _register(client, "assoc@firm.com", "associate")
    r = client.post("/api/clients/", headers=auth(asc),
                    json={"full_name": "Z", "email": "z@e.com"})
    assert r.status_code == 201, r.text
