"""
Phase A2 — password reset (request → token → reset → login).
SMTP is not configured in tests, so forgot-password returns a dev_token we can use.
"""

def _register(client, email="reset@firm.com", pw="OldPass123"):
    r = client.post("/api/auth/register", json={
        "full_name": "Reset User", "email": email, "password": pw, "role": "advocate"})
    assert r.status_code == 201, r.text


def test_full_reset_flow(client):
    _register(client, "reset@firm.com", "OldPass123")

    # request reset → dev_token returned (no SMTP in tests)
    r = client.post("/api/auth/forgot-password", json={"email": "reset@firm.com"})
    assert r.status_code == 200
    token = r.json().get("dev_token")
    assert token, "dev_token should be present when email is not configured"

    # reset to a new password
    r = client.post("/api/auth/reset-password",
                    json={"token": token, "new_password": "BrandNew456"})
    assert r.status_code == 200

    # old password no longer works; new one does
    assert client.post("/api/auth/login",
                       json={"email": "reset@firm.com", "password": "OldPass123"}).status_code == 401
    ok = client.post("/api/auth/login",
                     json={"email": "reset@firm.com", "password": "BrandNew456"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]


def test_forgot_password_unknown_email_is_generic(client):
    r = client.post("/api/auth/forgot-password", json={"email": "nobody@nowhere.com"})
    assert r.status_code == 200
    assert "dev_token" not in r.json()        # never hint that the email is unknown/known


def test_reset_with_bad_token_rejected(client):
    r = client.post("/api/auth/reset-password",
                    json={"token": "not-a-real-token", "new_password": "Whatever123"})
    assert r.status_code == 400


def test_reset_rejects_weak_password(client):
    _register(client, "weak@firm.com", "OldPass123")
    token = client.post("/api/auth/forgot-password",
                        json={"email": "weak@firm.com"}).json()["dev_token"]
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "short"})
    assert r.status_code == 422        # pydantic validation (min 8 chars)
