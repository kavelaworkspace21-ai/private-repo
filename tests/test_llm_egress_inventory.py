"""Every point where client data can leave for a model is inventoried and consent-gated.

S5 asks to *enumerate every LLM egress* and *prove consent is checked at each boundary*.
`tests/test_ai_consent_boundary.py` already proves the behaviour thoroughly — refusal without
consent, withdrawal taking effect immediately, an out-of-date policy version not counting, the
payload not even being built. What it cannot do is notice a **new** egress: its check is

    missing = expected - gated

which asserts that known handlers are gated and says nothing at all about a tenth one added
next month. That is the shape of a check that reports nothing, and this codebase has been
bitten by it repeatedly.

So this file inventories the egress points themselves, by parsing the source. Adding a call to
a model anywhere under `app/` fails this test until the author records it here and states how
consent is enforced for it. The list is the deliverable; the test is what keeps it true.

Consent is enforced at the ROUTE, via `require_ai_consent` (`app/auth/dependencies.py`), which
is why several egress points sit in service modules with no gate of their own — they are
unreachable except through a gated route. Each entry below names that route.
"""
import ast
import pathlib

from fastapi.routing import APIRoute

from app.auth.dependencies import require_ai_consent
from app.main import app

APP_ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"

# Attribute-call suffixes that mean "data is going to a model provider".
EGRESS_MARKERS = ("completions", "transcriptions", "embeddings", "responses")

# THE INVENTORY. (module path, enclosing function) -> the consent-gated route that reaches it.
# Every entry was traced by hand on 2026-08-04. Adding a row is a deliberate act: it asserts
# that you followed the call path to a route carrying require_ai_consent.
KNOWN_EGRESS = {
    ("app/ai/agent.py", "stream_agent_response"):
        "POST /api/ai/chat",
    ("app/ai/case_law.py", "summarize_case"):
        "GET /api/research/cases/{tid}/summary",
    ("app/routers/ai_chat.py", "transcribe_audio"):
        "POST /api/ai/transcribe",
    ("app/routers/ai_drafting.py", "edit_selection"):
        "POST /api/drafting/edit",
    ("app/routers/ai_drafting.py", "review_own_draft"):
        "POST /api/drafting/review-draft",
    # `stream` is a generator nested inside generate_document, which carries the gate.
    ("app/routers/ai_drafting.py", "stream"):
        "POST /api/drafting/generate",
    ("app/routers/library.py", "summarize_section"):
        "GET /api/library/acts/{act_id}/sections/{num}/summary",
    ("app/services/workbench/engine.py", "_llm_generate"):
        "POST /api/workbench/sessions/{session_id}/generate",
    ("app/services/workbench/uploads.py", "answer_from_file"):
        "POST /api/workbench/uploads/{upload_id}/chat",
}


def _enclosing_function(node, parents):
    cur = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur.name
    return "<module>"


def _discover_egress():
    """Every `*.completions/transcriptions/embeddings/responses.create(...)` call under app/."""
    found = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:                      # pragma: no cover
            continue
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            src = ast.unparse(node.func)
            if src.endswith(".create") and any(m in src for m in EGRESS_MARKERS):
                rel = path.relative_to(APP_ROOT.parent).as_posix()
                found[(rel, _enclosing_function(node, parents))] = node.lineno
    return found


def _consent_gated_routes():
    def walk(routes, prefix=""):
        for r in routes:
            if isinstance(r, APIRoute):
                yield prefix + r.path, r
            elif type(r).__name__ == "_IncludedRouter":
                yield from walk(r.original_router.routes,
                                prefix + (r.include_context.prefix or ""))

    def flat(d):
        yield d
        for s in d.dependencies:
            yield from flat(s)

    gated = set()
    for path, route in walk(app.routes):
        if any(d.call is require_ai_consent for d in flat(route.dependant)):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                gated.add(f"{method} {path}")
    return gated


def test_no_undeclared_llm_egress_exists():
    """A new model call anywhere under app/ fails until it is inventoried.

    This is the check test_ai_consent_boundary cannot make: it verifies known handlers are
    gated, and is silent about ones that did not exist when it was written.
    """
    discovered = _discover_egress()
    undeclared = {k: v for k, v in discovered.items() if k not in KNOWN_EGRESS}
    assert not undeclared, (
        "new LLM egress found that is not in KNOWN_EGRESS:\n  "
        + "\n  ".join(f"{m}:{line} in {fn}()" for (m, fn), line in sorted(undeclared.items()))
        + "\n\nTrace the call path to the route that reaches it, confirm that route depends on "
          "require_ai_consent, then add a row naming that route. Do not add a row to silence "
          "this."
    )


def test_the_inventory_has_no_stale_entries():
    """An entry for code that no longer exists hides the fact that coverage moved.

    Without this, a refactor that renames the function would leave the inventory looking
    complete while the real egress went undeclared — and the test above would then be the only
    thing that noticed, one release too late.
    """
    discovered = _discover_egress()
    stale = sorted(set(KNOWN_EGRESS) - set(discovered))
    assert not stale, (
        "KNOWN_EGRESS lists call sites that no longer exist: "
        + ", ".join(f"{m}::{fn}" for m, fn in stale))


def test_every_inventoried_egress_names_a_route_that_is_actually_consent_gated():
    """The inventory's claims are checked against the live route table, not trusted.

    A row asserting "reached via POST /api/ai/chat" is worthless if that route stopped
    depending on require_ai_consent. This resolves every named route against the running app
    and fails if the gate is gone.
    """
    gated = _consent_gated_routes()
    broken = {site: route for site, route in KNOWN_EGRESS.items() if route not in gated}
    assert not broken, (
        "these egress points name a route that is NOT consent-gated in the live app:\n  "
        + "\n  ".join(f"{m}::{fn}  claims  {route}" for (m, fn), route in sorted(broken.items()))
        + "\n\nConsent-gated routes are:\n  " + "\n  ".join(sorted(gated))
    )


def test_the_discovery_actually_finds_things():
    """Guards the scanner itself.

    If the AST walk broke — a marker renamed upstream, a parse failure swallowed — every test
    above would pass while inspecting nothing. Assert a known-present egress is still seen.
    """
    discovered = _discover_egress()
    assert len(discovered) >= 9, f"only {len(discovered)} egress points found; scanner broken"
    assert ("app/ai/agent.py", "stream_agent_response") in discovered
