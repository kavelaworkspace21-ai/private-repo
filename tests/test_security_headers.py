"""
Phase B hardening — every HTTP response carries baseline security headers (clickjacking, MIME-sniffing,
referrer leakage, feature lock-down, HSTS, CSP). The API docs are exempt from the strict CSP so Swagger
still renders. Satisfies LSAI-SKILL-09 "security headers test".
"""


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.status_code == 200
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer"
    assert "geolocation=()" in h["Permissions-Policy"]
    assert "max-age=" in h["Strict-Transport-Security"]
    assert "default-src 'self'" in h["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]


def test_csp_exempt_on_docs(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "Content-Security-Policy" not in r.headers          # docs exempt so Swagger CDN works
    assert r.headers["X-Content-Type-Options"] == "nosniff"    # but other headers still applied
