"""Personal data must not leave the system through telemetry or client-side storage.

Two leaks this pins:

  * Sentry. `send_default_pii=False` covers IP/cookies/headers but NOT stack-frame local
    variables — and the frame that raises is precisely the one holding `password`, `email`
    and client matter text. Local variables are now off and a before_send hook scrubs the
    rest.
  * localStorage. `/api/auth/me` returns email, phone and professional_id; the nav chip
    cached the whole object while reading only three fields. Anything in localStorage is
    readable by any script on the page.
"""
import json
import pathlib

from app.observability import _SCRUBBED, _scrub, _scrub_event

STATIC = pathlib.Path(__file__).resolve().parent.parent / "app" / "static"


# ── Sentry scrubbing ────────────────────────────────────────────────────────────
def test_scrub_removes_credentials_and_contact_details():
    payload = {"email": "advocate@firm.com", "password": "Sup3rSecret!",
               "phone": "9876500000", "case_ref": "CS/123/2026"}
    out = _scrub(payload)
    assert out["email"] == _SCRUBBED
    assert out["password"] == _SCRUBBED
    assert out["phone"] == _SCRUBBED
    assert out["case_ref"] == "CS/123/2026", "non-personal fields should survive"


def test_scrub_reaches_nested_structures():
    payload = {"user": {"profile": {"email": "a@b.com"}}, "items": [{"token": "abc123"}]}
    out = _scrub(payload)
    assert out["user"]["profile"]["email"] == _SCRUBBED
    assert out["items"][0]["token"] == _SCRUBBED


def test_scrub_removes_the_ai_prompt_which_carries_client_facts():
    """An advocate's question is the most sensitive payload in the app."""
    payload = {"message": "Anticipatory bail for Ramesh Kumar in the Acme fraud matter"}
    assert _scrub(payload)["message"] == _SCRUBBED


def test_scrub_is_depth_capped_and_survives_odd_input():
    deep = cur = {}
    for _ in range(30):
        cur["nested"] = {}
        cur = cur["nested"]
    _scrub(deep)          # must return rather than recurse without bound
    assert _scrub("plain string") == "plain string"
    assert _scrub(None) is None


def test_scrub_event_cleans_request_body_and_breadcrumbs():
    event = {
        "request": {"data": {"password": "hunter2", "email": "x@y.com"},
                    "headers": {"Authorization": "Bearer abc"},
                    "cookies": {"session": "s3cr3t"}},
        "breadcrumbs": [{"data": {"phone": "9876500000"}}],
        "extra": {"full_name": "Ramesh Kumar"},
    }
    out = _scrub_event(event, None)
    assert out["request"]["data"]["password"] == _SCRUBBED
    assert out["request"]["data"]["email"] == _SCRUBBED
    assert out["request"]["headers"]["Authorization"] == _SCRUBBED
    assert out["breadcrumbs"][0]["data"]["phone"] == _SCRUBBED
    assert out["extra"]["full_name"] == _SCRUBBED


def test_scrub_event_never_raises_and_never_drops_the_report():
    """Returning None would discard the error entirely — the incident would vanish."""
    for bad in ({}, {"request": None}, {"request": {"data": "not-a-dict"}}, {"breadcrumbs": 5}):
        assert _scrub_event(dict(bad), None) is not None


def test_sentry_is_configured_to_withhold_local_variables():
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "app" / "observability.py").read_text(encoding="utf-8")
    assert "include_local_variables=False" in src, (
        "stack-frame locals hold passwords and client text at the moment of failure")
    assert "send_default_pii=False" in src
    assert "before_send=_scrub_event" in src


# ── Client-side storage ─────────────────────────────────────────────────────────
def test_localstorage_user_cache_holds_no_contact_details():
    js = (STATIC / "utils.js").read_text(encoding="utf-8")
    # the cache is built from an explicit allow-list, not the whole /me response
    assert "full_name: me.full_name" in js
    assert "me.email" not in js, "email is being written to localStorage"
    assert "me.phone" not in js, "phone is being written to localStorage"
    assert "JSON.stringify(me)" not in js, "the whole profile is being cached"


def test_stale_cached_profiles_are_purged_not_just_stopped():
    """Existing browsers already hold the full object; writing less would leave it there."""
    js = (STATIC / "utils.js").read_text(encoding="utf-8")
    assert "'email' in user" in js, "no purge path for profiles cached by an earlier build"


def test_service_worker_version_bumped_for_the_utils_change():
    """utils.js is served cache-first; without a version bump users keep the old file."""
    sw = (STATIC / "service-worker.js").read_text(encoding="utf-8")
    assert "juriscite-v12" in sw
