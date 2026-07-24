"""
Lightweight in-memory rate limiter (no external deps).

Protects abuse-/cost-sensitive endpoints (login, password reset, AI calls). Keyed by
client IP + a route name, sliding window. In-process only — fine for the single-instance
beta; when we move to multi-process/Postgres (Phase B) this should move to Redis.

Disabled when env RATELIMIT_ENABLED != "1" (tests run with it off to avoid cross-test
contamination; the limiter's algorithm is unit-tested directly).
"""
import os
import time
import threading
from fastapi import Request, HTTPException

_BUCKETS: dict[str, list[float]] = {}
_LOCK = threading.Lock()
_MAX_KEYS = 10_000


def enabled() -> bool:
    return os.getenv("RATELIMIT_ENABLED", "1") == "1"


def reset() -> None:
    with _LOCK:
        _BUCKETS.clear()


def _allow(key: str, limit: int, window: float, now: float | None = None) -> bool:
    """True if this hit is within the limit for the sliding window; records the hit."""
    now = now if now is not None else time.time()
    with _LOCK:
        if len(_BUCKETS) > _MAX_KEYS:        # guard against unbounded growth
            _BUCKETS.clear()
        hits = [t for t in _BUCKETS.get(key, []) if now - t < window]
        if len(hits) >= limit:
            _BUCKETS[key] = hits
            return False
        hits.append(now)
        _BUCKETS[key] = hits
        return True


class RateLimiter:
    """FastAPI dependency: raises 429 when an IP exceeds `limit` hits per `window` seconds."""

    def __init__(self, limit: int, window: int, name: str):
        self.limit, self.window, self.name = limit, window, name

    def __call__(self, request: Request):
        if not enabled():
            return
        ip = request.client.host if request.client else "unknown"
        if not _allow(f"{self.name}:{ip}", self.limit, self.window):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait a moment and try again.",
            )


# Shared limiter instances
login_limiter   = RateLimiter(20, 300, "login")      # 20 / 5 min per IP
forgot_limiter  = RateLimiter(5, 900, "forgot")      # 5 / 15 min per IP
register_limiter = RateLimiter(10, 3600, "register")  # 10 / hour per IP
ai_limiter      = RateLimiter(40, 60, "ai")          # 40 / min per IP (cost control)
