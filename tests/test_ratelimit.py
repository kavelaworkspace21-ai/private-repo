"""
Rate limiter — algorithm unit tests (deterministic; no HTTP, no shared-IP contamination).
The limiter is disabled in the API test env on purpose (see conftest).
"""
from app.services import ratelimit


def setup_function(_):
    ratelimit.reset()


def test_allows_up_to_limit_then_blocks():
    for i in range(5):
        assert ratelimit._allow("k", limit=5, window=60) is True, f"hit {i} should pass"
    assert ratelimit._allow("k", limit=5, window=60) is False   # 6th blocked


def test_window_expiry_frees_capacity():
    base = 1000.0
    for _ in range(3):
        assert ratelimit._allow("w", 3, 60, now=base) is True
    assert ratelimit._allow("w", 3, 60, now=base + 1) is False      # still within window
    assert ratelimit._allow("w", 3, 60, now=base + 61) is True      # window elapsed → allowed


def test_keys_are_independent():
    assert ratelimit._allow("a", 1, 60) is True
    assert ratelimit._allow("a", 1, 60) is False
    assert ratelimit._allow("b", 1, 60) is True     # different key unaffected


def test_disabled_in_test_env():
    assert ratelimit.enabled() is False             # conftest sets RATELIMIT_ENABLED=0
