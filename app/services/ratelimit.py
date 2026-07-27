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


# Shared limiter instances.
#
# Credential endpoints are tightened to the pre-deploy thresholds. The previous login limit
# (20 per 5 min) permitted a 20-request burst — enough to walk a short password list against
# a known advocate's email before the window closed. 5 per minute keeps a mistyped password
# workable while making online guessing useless.
#
# NOTE (single-node only): buckets live in this process's memory, so N app instances behind a
# load balancer multiply every limit by N, and a restart clears them. Moving to a shared store
# (Redis) is required before horizontal scaling — tracked in docs/OWNER_QUEUE.md.
login_limiter   = RateLimiter(5, 60, "login")        # 5 / min per IP
forgot_limiter  = RateLimiter(3, 3600, "forgot")     # 3 / hour per IP (reset emails)
register_limiter = RateLimiter(10, 3600, "register")  # 10 / hour per IP
ai_limiter      = RateLimiter(40, 60, "ai")          # 40 / min per IP (cost control)

# TOTP verification was UNLIMITED. A 6-digit code is one million combinations, but a code
# stays valid for a ~30-90s window, so an attacker who already has the password (and thus a
# temp_token) could spray guesses at that window until one lands — defeating the second
# factor entirely while looking like ordinary traffic. 5 attempts per 5 minutes leaves room
# for clock drift and a fat-fingered code, and nothing else.
otp_limiter     = RateLimiter(5, 300, "otp")         # 5 / 5 min per IP
# Consuming a reset token was also unlimited; rate-limit the guessing surface regardless of
# token entropy.
reset_limiter   = RateLimiter(5, 3600, "reset")      # 5 / hour per IP
