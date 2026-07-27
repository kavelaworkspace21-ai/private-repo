"""
Production observability — request IDs, optional Sentry error tracking, log level control.

All optional and guarded:
  • Request IDs work always (X-Request-ID on every response; correlate logs/support).
  • Sentry activates ONLY if SENTRY_DSN is set (no new hard dependency; import is guarded).
  • Logging stays compatible with uvicorn/pytest (we only set the level, never hijack handlers).
"""
import logging
import os
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Current request's correlation id (or '-' outside a request)."""
    return _request_id.get()


def internal_error(exc: Exception, *, status_code: int = 502, action: str,
                   hint: str = "") -> "HTTPException":
    """Log the real cause server-side; hand the client a generic message + correlation id.

    Broad `except Exception` blocks were interpolating the exception straight into the HTTP
    response. That text is not ours to publish: the OpenAI client raises with endpoint URLs
    and provider response bodies, and file operations raise with absolute server paths. The
    advocate cannot act on any of it, and an attacker can.

    The correlation id is the same X-Request-ID echoed on every response, so a user can quote
    it to support and the full traceback is one log search away.
    """
    from fastapi import HTTPException

    rid = get_request_id()
    logging.getLogger(__name__).exception("%s failed [request_id=%s]", action, rid)
    detail = f"{action} failed. Quote reference {rid} if you contact support."
    if hint:
        detail += f" {hint}"
    return HTTPException(status_code, detail)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign/propagate an X-Request-ID for every request and echo it on the response."""

    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = _request_id.set(rid)
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


def configure_logging() -> None:
    """Set the root log level from LOG_LEVEL (default INFO). Safe — does not replace handlers."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.getLogger().setLevel(getattr(logging, level, logging.INFO))


# Values that must never leave the system inside an error report. Matched case-insensitively
# against dict KEYS, so nesting and unexpected shapes are still covered.
_SENSITIVE_KEYS = (
    "password", "passwd", "secret", "token", "authorization", "api_key", "apikey",
    "email", "phone", "address", "full_name", "totp", "gstin", "dob", "message",
    "content", "instructions", "query",
)
_SCRUBBED = "[REDACTED]"


def _scrub(obj, depth: int = 0):
    """Recursively replace sensitive values. Depth-capped so a cyclic/deep payload
    cannot spin here inside an error handler."""
    if depth > 6:
        return obj
    if isinstance(obj, dict):
        return {k: (_SCRUBBED if any(s in str(k).lower() for s in _SENSITIVE_KEYS)
                    else _scrub(v, depth + 1))
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_scrub(v, depth + 1) for v in obj)
    return obj


def _scrub_event(event, hint):
    """Sentry before_send hook — strip PII from the request payload and breadcrumbs.

    Never raises: an exception here would suppress the error report entirely, hiding the
    very incident we are trying to observe.
    """
    try:
        if "request" in event:
            req = event["request"]
            for field in ("data", "cookies", "headers", "query_string"):
                if field in req:
                    req[field] = _scrub(req[field]) if isinstance(req[field], (dict, list)) \
                        else _SCRUBBED
        if "breadcrumbs" in event:
            event["breadcrumbs"] = _scrub(event["breadcrumbs"])
        if "extra" in event:
            event["extra"] = _scrub(event["extra"])
    except Exception:
        pass
    return event


def init_sentry() -> bool:
    """Initialise Sentry iff SENTRY_DSN is set and the SDK is installed. Returns True if active."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            environment=os.getenv("ENVIRONMENT", "production"),
            send_default_pii=False,   # no IP / cookies / headers
            # send_default_pii=False does NOT stop PII reaching Sentry: the SDK also ships
            # local variables from every stack frame, and the frames that raise are exactly
            # the ones holding `password`, `email` and client matter text. Turn that off and
            # scrub what remains — for a legal product, an error tracker holding a client's
            # details is a disclosure, not telemetry.
            include_local_variables=False,
            before_send=_scrub_event,
        )
        return True
    except Exception:
        logging.getLogger(__name__).warning("SENTRY_DSN set but sentry-sdk unavailable; skipping.")
        return False
