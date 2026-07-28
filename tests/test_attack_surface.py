"""Adversarial checks — the attacks, encoded so they stay closed.

Written after probing a running instance rather than only reading code. Most of these
document a PASS: they exist so a future change cannot silently reopen the hole.
"""
import pytest

from tests.conftest import auth, register_and_login


# ── 1. ID manipulation (IDOR) ───────────────────────────────────────────────────
def test_foreign_ids_return_404_not_403(client):
    """404, not 403: a 403 confirms the record exists, which is itself a data leak.

    An attacker walking /api/cases/1..N could otherwise map how many matters a firm has
    and when they were created, without ever reading one.
    """
    victim = register_and_login(client, "victim-idor@firm.com")
    attacker = register_and_login(client, "attacker-idor@firm.com")

    cid = client.post("/api/clients/", headers=auth(victim),
                      json={"full_name": "Confidential", "email": "c@x.com"}).json()["id"]
    case = client.post("/api/cases/", headers=auth(victim),
                       json={"title": "SECRET", "client_id": cid,
                             "case_type": "civil", "court": "HC"}).json()["id"]

    for path in (f"/api/clients/{cid}", f"/api/cases/{case}"):
        r = client.get(path, headers=auth(attacker))
        assert r.status_code == 404, f"{path} leaked existence with {r.status_code}"

    assert client.get("/api/cases/", headers=auth(attacker)).json() == []
    assert client.get("/api/clients/", headers=auth(attacker)).json() == []


# ── 2. Login bypass ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "", "null", "undefined", "Bearer", "a.b.c",
    "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIiwicm9sZSI6ImZpcm1fYWRtaW4ifQ.",  # alg=none
])
def test_malformed_and_unsigned_tokens_are_refused(client, bad):
    """Includes the classic alg=none forgery: a token with no signature at all."""
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_protected_endpoints_require_a_token(client):
    for path in ("/api/auth/me", "/api/cases/", "/api/clients/", "/api/admin/status"):
        assert client.get(path).status_code == 401, f"{path} served without auth"


def test_only_public_legal_pages_are_unauthenticated():
    """Structural: the unauthenticated /api surface must stay exactly the public documents."""
    from app.main import app

    AUTH = {"get_current_user", "require_ai_user", "require_ai_access", "require_ai_consent",
            "require_founder", "require_matter_write", "require_billing_admin",
            "current_tenant_id", "require_advocate", "require_firm_admin"}

    def walk(routes):
        for r in routes:
            o = getattr(r, "original_router", None)
            if o is not None:
                yield from walk(o.routes)
            elif hasattr(r, "dependant"):
                yield r

    def names(dep, acc=None):
        acc = acc if acc is not None else set()
        for sub in dep.dependencies:
            c = getattr(sub, "call", None)
            if c is not None:
                acc.add(getattr(c, "__name__", type(c).__name__))
            names(sub, acc)
        return acc

    open_paths = {r.path for r in walk(app.routes)
                  if r.path.startswith("/api/") and not (names(r.dependant) & AUTH)}
    assert open_paths <= {"/api/legal/doc/{slug}", "/api/legal/identity", "/api/legal/index"}, (
        f"new unauthenticated API surface: {open_paths}")


# ── 3. Privilege escalation ─────────────────────────────────────────────────────
def test_forged_role_in_a_validly_signed_token_grants_nothing(client):
    """The strongest version of this attack: the token is signed with the REAL key and
    claims firm_admin. It must still fail, because authorisation reads the role from the
    database, never from the token."""
    from datetime import timedelta

    from app.auth.security import _create_token, decode_token

    r = client.post("/api/auth/register", json={
        "full_name": "Clerk", "email": "escalate@firm.com",
        "password": "Sup3rSecret!", "role": "clerk"})
    assert r.status_code == 201
    genuine = client.post("/api/auth/login",
                          json={"email": "escalate@firm.com",
                                "password": "Sup3rSecret!"}).json()["access_token"]
    sub = decode_token(genuine)["sub"]
    forged = _create_token({"sub": sub, "role": "firm_admin", "type": "access"},
                           timedelta(hours=1))

    body = {"full_name": "X", "email": "x@x.com"}
    assert client.post("/api/clients/", headers=auth(genuine), json=body).status_code == 403
    assert client.post("/api/clients/", headers=auth(forged), json=body).status_code == 403, (
        "role escalation via the JWT claim succeeded")


def test_founder_endpoints_are_closed_without_the_admin_token(client):
    tok = register_and_login(client, "notfounder@firm.com")
    assert client.post("/api/library/corpus-check-updates",
                       headers=auth(tok)).status_code == 403


# ── 6. Internal exposure ────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", [
    "/.env", "/static/../.env", "/static/../../.env", "/.git/config",
    "/RELEASE.json", "/legal_server.db", "/.secrets.baseline", "/alembic.ini",
])
def test_sensitive_files_are_not_reachable_over_http(client, path):
    assert client.get(path).status_code in (404, 405), f"{path} is served"


def test_health_endpoints_expose_no_internals(client):
    body = client.get("/healthz").text + client.get("/readyz").text
    for leak in ("/srv", "C:\\", "D:\\", "password", "secret", "postgresql://", "sqlite:///"):
        assert leak.lower() not in body.lower(), f"health endpoint leaked {leak!r}"


# ── 7. Business-logic manipulation ──────────────────────────────────────────────
@pytest.mark.parametrize("amount", [-50000, -0.01, 1e15])
def test_fee_amounts_reject_negative_and_absurd_values(amount):
    """Negative receipts silently corrupt outstanding-balance and revenue totals. These are
    the advocate's own ledger entries, so this is data integrity, not theft from the
    platform — but a compromised account or a malicious clerk could wreck the books."""
    from pydantic import ValidationError

    from app.schemas.fee import FeeCollectedCreate
    with pytest.raises(ValidationError):
        FeeCollectedCreate(case_id=1, amount=amount, payment_date="2026-07-25")


def test_legitimate_fee_amounts_still_work():
    """Over-tightening would be its own bug: zero is a legitimately waived fee."""
    from app.schemas.fee import FeeCollectedCreate
    assert FeeCollectedCreate(case_id=1, amount=25000.50,
                              payment_date="2026-07-25").amount == 25000.50
    assert FeeCollectedCreate(case_id=1, amount=0, payment_date="2026-07-25").amount == 0


def test_seat_count_cannot_be_negative_or_unbounded():
    from pydantic import ValidationError

    from app.schemas.billing import CheckoutRequest
    for seats in (-1, 0, 10_000):
        with pytest.raises(ValidationError):
            CheckoutRequest(plan_code="solo", billing_cycle="monthly", seats=seats)


def test_trial_creation_is_idempotent_per_tenant(client):
    """Calling it twice must not stack a second trial period."""
    from app.db.session import get_db
    from app.main import app as fastapi_app
    from app.models.user import User
    from app.services.billing import start_trial

    register_and_login(client, "trialabuse@firm.com")
    db = next(fastapi_app.dependency_overrides[get_db]())
    tid = db.query(User).filter(User.email == "trialabuse@firm.com").first().tenant_id

    first = start_trial(db, tid)
    second = start_trial(db, tid)
    assert first.id == second.id, "a second trial row was created for the same tenant"
