"""Post-deploy smoke test — run this against a LIVE deployment.

    python scripts/smoke_test.py https://app.example.com

S3 asks for a smoke-test suite, database health checks, release-identity verification and
application-startup verification. This is all four, executable, because a checklist that says
"verify the app is healthy" is a checklist nobody can fail.

What it is NOT: a load test, and not a substitute for the pytest suite. It answers one
question — *is the thing that just deployed actually serving correctly?* — from outside the
process, over HTTP, the way a user reaches it.

DESIGN RULES, each of which this project has learned the hard way:

  * **Fails closed.** Any check that cannot be performed counts as a failure, never a pass.
    Exit code is non-zero if a single REQUIRED check fails, so CI or a deploy script can gate
    on it. A smoke test that cannot fail is worse than none, because it reads as assurance.
  * **Creates no data.** It never registers a user, never writes a matter. A smoke test that
    seeds rows into a production database is a data-integrity problem wearing a hard hat.
  * **Prints no secrets.** Config is reported as presence booleans, which is all
    /api/admin/status returns anyway.
  * **Says what it checked**, including the checks it SKIPPED and why, so a green run is not
    mistaken for a more thorough one than it was.

Exit codes:  0 = all required checks passed · 1 = a required check failed · 2 = usage error
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 15
# The first /readyz on a cold process loads the Chroma store and the ONNX model.
READY_TIMEOUT = 60


class Result:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []   # (status, name, detail)
        self.failed = 0

    def record(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))
        if status == "FAIL":
            self.failed += 1

    def ok(self, name, detail=""):
        self.record("PASS", name, detail)

    def bad(self, name, detail=""):
        self.record("FAIL", name, detail)

    def skip(self, name, detail=""):
        self.record("SKIP", name, detail)

    def warn(self, name, detail=""):
        self.record("WARN", name, detail)


def _get(base: str, path: str, token: str | None = None,
         timeout: int = TIMEOUT) -> tuple[int, dict | str]:
    """GET base+path. Returns (status_code, parsed_body). Never raises."""
    req = urllib.request.Request(base.rstrip("/") + path, method="GET")
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 - operator-supplied URL
            raw = resp.read().decode("utf-8", "replace")
            code = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        code = exc.code
    except Exception as exc:                       # DNS, TLS, refused, timeout
        return 0, f"{type(exc).__name__}: {exc}"
    try:
        return code, json.loads(raw)
    except json.JSONDecodeError:
        return code, raw[:400]


def _get_with_retry(base: str, path: str, attempts: int = 5,
                    timeout: int = READY_TIMEOUT) -> tuple[int, dict | str]:
    """GET, retrying while the instance is still warming.

    The FIRST /readyz on a freshly-booted process opens the Chroma persistent store and loads
    the ONNX embedding model. Measured on the dev box: 3.95 s cold against 0.03 s warm, and
    observed once to exceed 15 s under concurrent load. Treating that first slow response as a
    failure would mean the smoke test reports a healthy deployment as broken purely for having
    been asked too early — and it is the same reason a readiness probe needs a generous
    timeout (see the probe guidance in AURORA_DEPLOYMENT_RUNBOOK.md).
    """
    last: tuple[int, dict | str] = (0, "no attempt made")
    for attempt in range(attempts):
        last = _get(base, path, timeout=timeout)
        if last[0] != 0:
            return last
        if attempt < attempts - 1:
            time.sleep(2 * (attempt + 1))          # 2s, 4s, 6s, 8s
    return last


# ── checks ─────────────────────────────────────────────────────────────────────

def check_liveness(base: str, r: Result) -> None:
    """/healthz — process up, soul intact, DATABASE ANSWERS.

    This is the database health check: healthz executes `SELECT 1` through the app's own
    session, so it proves the configured DATABASE_URL resolves, authenticates, and serves —
    from inside the deployed process, which is the only place that matters.
    """
    code, body = _get(base, "/healthz")
    if code == 0:
        return r.bad("liveness /healthz", f"unreachable — {body}")
    if not isinstance(body, dict):
        return r.bad("liveness /healthz", f"HTTP {code}, non-JSON body: {body}")

    if code == 200 and body.get("status") == "ok":
        r.ok("liveness /healthz", f"version={body.get('version')}")
    else:
        r.bad("liveness /healthz", f"HTTP {code} status={body.get('status')}")

    # Report the components individually — "unhealthy" alone does not say which half.
    if body.get("db") == "ok":
        r.ok("database reachable from the app", "SELECT 1 via the app's own session")
    else:
        r.bad("database reachable from the app", f"db={body.get('db')!r}")

    if body.get("soul") == "intact":
        r.ok("soul integrity", "intact")
    else:
        r.bad("soul integrity", f"soul={body.get('soul')!r}")


def check_readiness(base: str, r: Result) -> None:
    """/readyz — the vector index is actually built and matches the pinned count."""
    code, body = _get_with_retry(base, "/readyz")
    if code == 0 or not isinstance(body, dict):
        return r.bad("readiness /readyz", f"unreachable or non-JSON — {body}")

    idx = body.get("vector_index") or {}
    chunks, expected = idx.get("chunks"), idx.get("expected")

    if code == 200 and body.get("status") == "ready":
        r.ok("readiness /readyz", f"chunks={chunks} model={body.get('embedding_model')}")
    else:
        r.bad("readiness /readyz",
              f"HTTP {code} status={body.get('status')} chunks={chunks} expected={expected}")

    # An index that is BUILT but the wrong size still answers /readyz 200 (it only requires
    # chunks > 0). Retrieval would silently draw on a different corpus than the audited one.
    if chunks is not None and expected is not None:
        if chunks == expected:
            r.ok("vector index matches the pinned count", f"{chunks} chunks")
        else:
            r.bad("vector index matches the pinned count",
                  f"live {chunks} != pinned {expected} — corpus drift; run preflight")
    else:
        r.bad("vector index matches the pinned count", "counts not reported by /readyz")


def check_release_identity(base: str, r: Result, token: str | None) -> None:
    """Is the deployed build the audited release?

    /api/admin/status returns live_status() — the same values preflight compares against
    RELEASE.json. Requires a firm-admin token. Without one this is SKIPPED and said so, never
    silently passed: an unverifiable identity is not a verified one.
    """
    release_path = REPO_ROOT / "RELEASE.json"
    if not release_path.exists():
        return r.bad("release identity", "RELEASE.json not found next to this script")
    pinned = json.loads(release_path.read_text(encoding="utf-8"))

    if not token:
        return r.skip(
            "release identity (deployed build == RELEASE.json)",
            "no --admin-token given; /api/admin/status is firm-admin only. "
            f"Expected app_version={pinned.get('app_version')} "
            f"corpus={pinned.get('corpus_fingerprint')} head={pinned.get('migration_head')}")

    code, live = _get(base, "/api/admin/status", token=token)
    if code == 401 or code == 403:
        return r.bad("release identity", f"HTTP {code} — admin token rejected")
    if code != 200 or not isinstance(live, dict):
        return r.bad("release identity", f"HTTP {code}: {live}")

    for field, pin_key in (("app_version", "app_version"),
                           ("corpus_fingerprint", "corpus_fingerprint"),
                           ("migration_head", "migration_head")):
        live_val, pin_val = live.get(field), pinned.get(pin_key)
        if live_val == pin_val:
            r.ok(f"release identity: {field}", str(live_val))
        else:
            r.bad(f"release identity: {field}", f"live {live_val!r} != pinned {pin_val!r}")

    # Presence booleans only — live_status() never returns secret VALUES.
    cfg = live.get("config", {}) or {}
    for key in ("JWT_SECRET", "FIELD_ENCRYPTION_KEY", "DATABASE_URL"):
        if cfg.get(key):
            r.ok(f"config present: {key}", "set (value never read)")
        else:
            r.bad(f"config present: {key}", "NOT SET")


def check_auth_is_enforced(base: str, r: Result) -> None:
    """An unauthenticated request to a protected route must be refused.

    The cheapest possible check that authentication is actually wired in the deployed build,
    and it writes nothing. A 200 here would mean the app is serving tenant data to anyone.
    """
    for path in ("/api/clients", "/api/cases", "/api/admin/status"):
        code, _ = _get(base, path)
        if code in (401, 403):
            r.ok(f"auth enforced on {path}", f"HTTP {code}")
        elif code == 0:
            r.bad(f"auth enforced on {path}", "unreachable")
        else:
            r.bad(f"auth enforced on {path}",
                  f"HTTP {code} — expected 401/403 for an unauthenticated request")


def check_docs_are_closed(base: str, r: Result, is_local: bool) -> None:
    """Reachable /docs means the app is NOT running as production. That is the real finding.

    There is no separate docs toggle: `app/main.py` sets
    `_DOCS_ENABLED = not _is_production()` at import time. So a reachable /docs does not merely
    mean the API surface is published — it proves `_is_production()` returned False, and
    therefore that `assert_secrets_sane()` only **warned** about weak secrets and an
    unencrypted `sslmode` instead of refusing to boot. Every fail-closed gate is in warn mode.

    Hence FAIL on a remote deployment. On localhost it is expected (development is not
    production) and is reported as a WARN.
    """
    code, _ = _get(base, "/docs")
    if code in (404, 401, 403):
        return r.ok("API docs not public", f"HTTP {code} — app is running as production")
    if code == 0:
        return r.warn("API docs not public", "endpoint unreachable — inconclusive")

    detail = (f"HTTP {code} — /docs is reachable, so _is_production() is False. The boot gates "
              f"are in WARN mode: weak secrets and a plaintext sslmode would not have stopped "
              f"startup. Set ENVIRONMENT=production")
    if is_local:
        r.warn("API docs not public", detail + " (expected on localhost)")
    else:
        r.bad("API docs not public", detail)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Post-deploy smoke test against a live deployment.")
    ap.add_argument("base_url", help="e.g. https://app.example.com")
    ap.add_argument("--admin-token", default=None,
                    help="firm-admin bearer token; without it the release-identity check is "
                         "SKIPPED rather than passed")
    args = ap.parse_args(argv[1:])

    if not args.base_url.startswith(("http://", "https://")):
        print("base_url must start with http:// or https://", file=sys.stderr)
        return 2
    if args.base_url.startswith("http://") and "localhost" not in args.base_url:
        print("refusing to smoke-test a non-localhost deployment over plaintext http",
              file=sys.stderr)
        return 2

    is_local = "localhost" in args.base_url or "127.0.0.1" in args.base_url

    r = Result()
    check_liveness(args.base_url, r)
    check_readiness(args.base_url, r)
    check_release_identity(args.base_url, r, args.admin_token)
    check_auth_is_enforced(args.base_url, r)
    check_docs_are_closed(args.base_url, r, is_local)

    width = max(len(name) for _, name, _ in r.rows)
    print(f"\nSmoke test — {args.base_url}\n" + "=" * (width + 30))
    for status, name, detail in r.rows:
        print(f"  [{status}] {name.ljust(width)}  {detail}")

    skipped = sum(1 for s, _, _ in r.rows if s == "SKIP")
    warned = sum(1 for s, _, _ in r.rows if s == "WARN")
    passed = sum(1 for s, _, _ in r.rows if s == "PASS")
    print("=" * (width + 30))
    print(f"  {passed} passed, {r.failed} failed, {warned} warning(s), {skipped} skipped")
    if skipped:
        print("  NOTE: a skipped check was NOT verified. Green here is not green for those.")

    if r.failed:
        print("\nSMOKE TEST FAILED — do not announce this deployment as live.")
        return 1
    print("\nSmoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
