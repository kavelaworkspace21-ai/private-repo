"""Every route is either authenticated or explicitly declared public. No third option.

S5 asks for an audit of every tenant-scoped endpoint and a test of unauthorized resource
enumeration. A one-off audit answers for the day it was run; this enumerates the live route
table, so a NEW endpoint added without authentication fails the suite until somebody classifies
it deliberately.

**This test was written because that exact hole existed.** `diary_summary.diary_deadlines`
served `GET /api/diary/deadlines` with no authentication dependency and no tenant filter — its
entire dependency tree was `get_db` — and returned every firm's filing deadlines joined to
their case titles. It was unreachable only because `diary.router` is included before
`diary_summary.router` in main.py and registers the same path, so FastAPI matched the
protected handler first. The sole protection for every tenant's matter data was the order of
two lines in main.py, and nothing would have failed if that order changed.

Two things make the enumeration non-obvious, and both were got wrong first:

  * **Sub-router routes are not in `app.routes`.** Recent FastAPI keeps a `_IncludedRouter`
    holding a reference to the original router rather than copying routes into the parent, so
    a flat scan sees 36 routes out of 189. You have to recurse through `original_router` and
    carry the prefix.
  * **There are two authentication mechanisms.** Most routes reach `get_current_user`
    (directly, or through `current_tenant_id` / `require_role` / `require_ai_consent`), but
    the founder endpoints use `require_founder`, which checks an `X-Admin-Token` header and
    never touches `get_current_user`. Looking only for the first reports the admin
    verification endpoints as unprotected.
"""
from fastapi.routing import APIRoute

from app.auth.dependencies import get_current_user, require_founder
from app.main import app

# Anything whose dependency tree reaches one of these is authenticated.
# `require_role`, `require_firm_admin`, `require_matter_write`, `require_ai_consent` and
# `current_tenant_id` all resolve to get_current_user, so listing it covers them.
AUTH_DEPENDENCIES = {get_current_user, require_founder}

# Routes that are public BY DESIGN. Every entry is a decision, and adding one should feel like
# a decision — that is the point of making the list explicit rather than pattern-matched.
PUBLIC_ROUTES = {
    # Health and readiness probes — a load balancer cannot authenticate.
    ("GET", "/health"),
    ("GET", "/healthz"),
    ("GET", "/readyz"),

    # Authentication entry points. These cannot require a session; they create one.
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/login/verify-2fa"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),

    # Public legal/policy documents — terms, privacy notice, governance identity. Published
    # deliberately; they contain no user data.
    ("GET", "/api/legal/index"),
    ("GET", "/api/legal/identity"),
    ("GET", "/api/legal/doc/{slug}"),

    # Public pricing. Plan definitions only, no subscriber data.
    ("GET", "/api/billing/plans"),

    # Payment provider webhook. Authenticated by SIGNATURE, not by a session — the caller is
    # Razorpay, which has no bearer token. See test_billing.py for the signature checks.
    ("POST", "/api/billing/webhook/razorpay"),

    # Static assets and PWA plumbing.
    ("GET", "/favicon.ico"),
    ("GET", "/manifest.webmanifest"),
    ("GET", "/service-worker.js"),
    ("GET", "/offline"),

    # HTML page shells. These serve markup only; every byte of user data on them arrives
    # later from the /api/ routes above, which are authenticated. A page shell being public
    # is not a data exposure — but it IS why each one is listed rather than pattern-matched
    # on "no /api/ prefix", which would have silently absolved a real API route.
    ("GET", "/"),
    ("GET", "/login"),
    ("GET", "/register"),
    ("GET", "/reset-password"),
    ("GET", "/setup-2fa"),
    ("GET", "/consent"),
    ("GET", "/pricing"),
    ("GET", "/legal"),
    ("GET", "/legal/{slug}"),
    ("GET", "/account"),
    ("GET", "/assistant"),
    ("GET", "/cases"),
    ("GET", "/diary"),
    ("GET", "/drafting"),
    ("GET", "/drafts"),
    ("GET", "/firm"),
    ("GET", "/library"),
    ("GET", "/notifications"),
    ("GET", "/workbench"),
}


def _walk(routes, prefix=""):
    """Yield (full_path, APIRoute, inclusion_dependencies) for EVERY route, recursively."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route, []
        elif type(route).__name__ == "_IncludedRouter":
            ctx = route.include_context
            inherited = list(ctx.dependencies or [])
            for path, sub, deps in _walk(route.original_router.routes,
                                         prefix + (ctx.prefix or "")):
                yield path, sub, deps + inherited


def _flatten(dependant):
    yield dependant
    for sub in dependant.dependencies:
        yield from _flatten(sub)


def _is_authenticated(route, inherited) -> bool:
    if any(d.call in AUTH_DEPENDENCIES for d in _flatten(route.dependant)):
        return True
    # Dependencies attached at include_router(dependencies=[...]) time are not on the route's
    # own dependant tree.
    return any(getattr(dep, "dependency", None) in AUTH_DEPENDENCIES for dep in inherited)


def _all_routes():
    out = []
    for path, route, inherited in _walk(app.routes):
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            out.append((method, path, route, inherited))
    return out


def test_every_route_is_authenticated_or_explicitly_public():
    """The gate. A new endpoint without auth fails here until it is classified."""
    unprotected = [
        (m, p) for m, p, route, inh in _all_routes()
        if not _is_authenticated(route, inh) and (m, p) not in PUBLIC_ROUTES
    ]
    assert not unprotected, (
        "these routes require no authentication and are not in PUBLIC_ROUTES:\n  "
        + "\n  ".join(f"{m:<7} {p}" for m, p in sorted(unprotected, key=lambda t: t[1]))
        + "\n\nAdd authentication, or add an entry to PUBLIC_ROUTES with a reason. Do not add "
          "an entry to make the suite pass."
    )


def test_the_enumeration_actually_sees_the_sub_router_routes():
    """Guards the enumeration itself.

    A flat `app.routes` scan finds 36 routes; recursing through `_IncludedRouter` finds 189.
    If FastAPI changes its internals and the recursion silently stops working, the test above
    would pass while checking almost nothing — the failure mode this whole file exists to
    prevent. So assert we can see routes that only exist inside included routers.
    """
    paths = {p for _, p, _, _ in _all_routes()}
    assert len(paths) > 100, f"only {len(paths)} routes enumerated — the recursion is broken"
    for expected in ("/api/clients", "/api/cases", "/api/documents/{doc_id}"):
        assert any(p == expected or p.startswith(expected) for p in paths), (
            f"{expected} was not enumerated; sub-router traversal is not working")


def test_public_route_list_has_no_stale_entries():
    """An entry that no longer matches a real route is dead weight that hides drift.

    If a route is renamed, its PUBLIC_ROUTES entry stops applying — and the renamed route
    silently needs re-classifying. Better to notice here.
    """
    live = {(m, p) for m, p, _, _ in _all_routes()}
    stale = PUBLIC_ROUTES - live
    assert not stale, (
        "PUBLIC_ROUTES lists routes that no longer exist:\n  "
        + "\n  ".join(f"{m:<7} {p}" for m, p in sorted(stale, key=lambda t: t[1])))


def test_no_duplicate_path_and_method_registrations():
    """Two handlers on one path+method mean one of them is shadowed and untested.

    This is precisely how `diary_summary.diary_deadlines` hid: it registered a second
    `GET /api/diary/deadlines`, was shadowed by the protected handler in diary.py, and so was
    unreachable, unauthenticated, un-tenant-scoped and invisible all at once. A shadowed
    handler is dead code that still executes the moment route ordering shifts.
    """
    seen: dict[tuple[str, str], list[str]] = {}
    for method, path, route, _ in _all_routes():
        key = (method, path)
        seen.setdefault(key, []).append(
            f"{route.endpoint.__module__}.{route.endpoint.__name__}")

    duplicates = {k: v for k, v in seen.items() if len(v) > 1}
    assert not duplicates, (
        "the same path+method is registered by more than one handler; all but the first are "
        "shadowed:\n  "
        + "\n  ".join(f"{m} {p}  ->  {', '.join(fns)}" for (m, p), fns in duplicates.items()))


def test_unauthenticated_requests_to_tenant_data_are_refused(client):
    """End to end, over HTTP: the static analysis above must match real behaviour.

    Route enumeration proves the dependency is declared; this proves the server acts on it.
    """
    # Exact paths, taken from the live route table. An invented path 404s, and a 404 is not
    # evidence of anything — the first draft of this test asserted on /api/fees, which does
    # not exist, and would have "passed" the day authentication was removed from a real one.
    for path in ("/api/clients", "/api/cases", "/api/documents/", "/api/diary/deadlines",
                 "/api/diary/today", "/api/drafts/", "/api/fees/collected", "/api/fees/due",
                 "/api/hearings/"):
        r = client.get(path)
        assert r.status_code in (401, 403), (
            f"unauthenticated GET {path} returned {r.status_code}, expected 401/403")
