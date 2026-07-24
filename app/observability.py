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
            send_default_pii=False,   # never ship PII to the error tracker
        )
        return True
    except Exception:
        logging.getLogger(__name__).warning("SENTRY_DSN set but sentry-sdk unavailable; skipping.")
        return False
