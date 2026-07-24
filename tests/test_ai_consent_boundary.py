"""Consent must be enforced where client data actually leaves the system (DPDP 2023).

Before this gate, ConsentRecord was written at registration and read back for display, but
NOTHING checked it before a matter was sent to a third-party LLM. The audit recorded that as
an open G6 gap; these tests close it and keep it closed.

The case that motivated it: a firm-INVITED member (created by an admin, never asked to
accept anything) could use every AI feature without having granted consent.
"""
from app.auth.dependencies import require_ai_user
from app.db.session import get_db
from app.main import app
from app.models.consent import ConsentRecord
from app.models.user import User
from app.services.privacy import has_current_consent
from tests.conftest import auth, register_and_login


def _db():
    """Session bound to the test engine (same pattern as test_billing/test_entitlements)."""
    return next(app.dependency_overrides[get_db]())


def _uid(db, email: str) -> int:
    return db.query(User).filter(User.email == email).first().id


def _revoke(email: str) -> None:
    """Drop a user's current-version privacy consent — i.e. make them an invited member."""
    db = _db()
    db.query(ConsentRecord).filter(
        ConsentRecord.user_id == _uid(db, email),
        ConsentRecord.consent_type == "privacy_policy",
    ).delete(synchronize_session=False)
    db.commit()


# ── The helper both the UI and the gate rely on ─────────────────────────────────
def test_registration_grants_consent_at_current_version(client):
    register_and_login(client, "consented@firm.com")
    db = _db()
    assert has_current_consent(db, _uid(db, "consented@firm.com")) is True


def test_consent_at_an_old_policy_version_does_not_count(client):
    """Bumping PRIVACY_VERSION must invalidate prior consent — that is the point of versioning."""
    register_and_login(client, "stale@firm.com")
    db = _db()
    uid = _uid(db, "stale@firm.com")
    db.query(ConsentRecord).filter(ConsentRecord.user_id == uid).update(
        {"policy_version": "1999-01-01"}, synchronize_session=False)
    db.commit()
    assert has_current_consent(db, uid) is False


# ── The gate blocks the AI boundary ─────────────────────────────────────────────
def test_ai_chat_blocked_without_consent(client):
    tok = register_and_login(client, "noconsent-chat@firm.com")
    _revoke("noconsent-chat@firm.com")

    r = client.post("/api/ai/chat", headers=auth(tok),
                    json={"message": "What is section 138 of the NI Act?"})
    assert r.status_code == 403
    assert "consent" in r.json()["detail"].lower()
    assert "/consent" in r.json()["detail"], "the 403 must tell the user how to fix it"


def test_draft_generation_blocked_without_consent(client):
    tok = register_and_login(client, "noconsent-draft@firm.com")
    _revoke("noconsent-draft@firm.com")

    r = client.post("/api/drafting/generate", headers=auth(tok),
                    json={"document_type": "legal_notice", "title": "N",
                          "instructions": "draft a notice"})
    assert r.status_code == 403


def test_transcription_blocked_without_consent(client):
    """Audio is shipped to a third-party provider — same boundary, same rule."""
    tok = register_and_login(client, "noconsent-audio@firm.com")
    _revoke("noconsent-audio@firm.com")

    r = client.post("/api/ai/transcribe", headers=auth(tok),
                    files={"audio": ("a.wav", b"RIFF0000WAVE", "audio/wav")})
    assert r.status_code == 403


def test_non_ai_endpoints_stay_reachable_without_consent(client):
    """The gate guards the AI boundary only. Locking someone out of their own matter data
    would be a different, worse bug — and would stop them reaching the consent page."""
    tok = register_and_login(client, "noconsent-read@firm.com")
    _revoke("noconsent-read@firm.com")

    assert client.get("/api/cases/", headers=auth(tok)).status_code == 200
    assert client.get("/api/auth/needs-consent", headers=auth(tok)).status_code == 200
    assert client.get("/api/auth/needs-consent", headers=auth(tok)).json()["needs"] is True


def test_granting_consent_restores_ai_access(client):
    tok = register_and_login(client, "regrant@firm.com")
    _revoke("regrant@firm.com")
    assert client.post("/api/ai/chat", headers=auth(tok),
                       json={"message": "hello"}).status_code == 403

    assert client.post("/api/auth/consent", headers=auth(tok)).status_code in (200, 201)
    # now past the consent gate — whatever happens next, it is not a consent refusal
    r = client.post("/api/ai/chat", headers=auth(tok), json={"message": "hello"})
    assert r.status_code != 403


def test_no_external_payload_is_built_or_sent_without_consent(client, monkeypatch):
    """A 403 is not by itself proof. Assert the LLM client is never even constructed.

    The gate is a FastAPI dependency, so it runs before the handler body — payload
    assembly and the network call are both downstream of it. This records every attempt
    to build a client across the modules that make one, and requires zero.
    """
    import openai
    attempts: list[str] = []

    class _Tripwire:
        def __init__(self, *a, **k):
            attempts.append("client constructed")
            raise AssertionError("LLM client built without consent")

    monkeypatch.setattr(openai, "OpenAI", _Tripwire)
    monkeypatch.setattr(openai, "AsyncOpenAI", _Tripwire)

    tok = register_and_login(client, "nopayload@firm.com")
    _revoke("nopayload@firm.com")

    for method, path, kwargs in (
        ("post", "/api/ai/chat", {"json": {"message": "Confidential: client Ramesh v Acme"}}),
        ("post", "/api/drafting/generate",
         {"json": {"document_type": "legal_notice", "title": "N", "instructions": "x"}}),
        ("get", "/api/library/acts/ipc/sections/302/summary", {}),
    ):
        r = getattr(client, method)(path, headers=auth(tok), **kwargs)
        assert r.status_code == 403, f"{path} returned {r.status_code}, expected a consent refusal"

    assert attempts == [], f"an LLM client was constructed without consent: {attempts}"


# ── Structural guards: the invariant, not a path list ───────────────────────────
def _endpoint_deps():
    """(handler name, {dependency names}) for every route, walking included routers."""
    def walk(routes):
        for r in routes:
            orig = getattr(r, "original_router", None)
            if orig is not None:                       # FastAPI wraps included routers
                yield from walk(orig.routes)
            elif hasattr(r, "dependant"):
                yield r

    for r in walk(app.routes):
        names = {getattr(d.call, "__name__", type(d.call).__name__)
                 for d in r.dependant.dependencies if getattr(d, "call", None)}
        yield getattr(r.endpoint, "__name__", "?"), names


def test_no_route_depends_on_require_ai_access_directly():
    """The real invariant: verification must never be applied WITHOUT consent.

    Stated structurally rather than as a list of paths, so it keeps holding as routes are
    added or renamed — a new AI endpoint wired to the old dependency fails here.
    """
    offenders = [n for n, deps in _endpoint_deps() if "require_ai_access" in deps]
    assert offenders == [], (
        f"these endpoints take verification but skip the consent gate: {offenders}. "
        "Depend on require_ai_user instead.")


def test_the_known_llm_handlers_are_gated():
    """Names, not paths — a prefix change must not silently empty this check."""
    expected = {
        "chat", "transcribe_audio",                          # assistant + voice
        "generate_document", "edit_selection", "review_own_draft",   # drafting
        "create_session", "generate", "upload_file",         # workbench
        "upload_from_kanoon", "chat_with_file",
        "summarize_section",                                 # library AI summary
        "case_summary", "search_cases",                      # external research
    }
    gated = {n for n, deps in _endpoint_deps() if "require_ai_user" in deps}
    missing = expected - gated
    assert not missing, f"LLM handlers missing the consent gate: {sorted(missing)}"
