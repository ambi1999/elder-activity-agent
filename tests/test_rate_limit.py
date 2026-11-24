"""Request limits: uploads per device (ADR 0020) and sign-in requests (ADR 0025), without a database.

Verifies: EA-FR-ING-008, EA-FR-AUTH-004
"""

from datetime import UTC, datetime, timedelta

from app.rate_limit import RateLimiter

NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)


def test_allows_up_to_the_limit_then_says_how_long_to_wait():
    limiter = RateLimiter()
    assert [limiter.check("phone", 3, NOW + timedelta(seconds=i)) for i in range(3)] == [None, None, None]
    assert limiter.check("phone", 3, NOW + timedelta(seconds=10)) == 50  # first request leaves the window at 60 s


def test_window_slides():
    limiter = RateLimiter()
    limiter.check("phone", 1, NOW)
    assert limiter.check("phone", 1, NOW + timedelta(seconds=30)) is not None
    assert limiter.check("phone", 1, NOW + timedelta(seconds=61)) is None


def test_devices_are_counted_separately():
    limiter = RateLimiter()
    limiter.check("a", 1, NOW)
    assert limiter.check("b", 1, NOW) is None


def test_refused_requests_are_not_counted():
    limiter = RateLimiter()
    limiter.check("phone", 1, NOW)
    for _ in range(5):
        limiter.check("phone", 1, NOW + timedelta(seconds=1))
    assert limiter.check("phone", 1, NOW + timedelta(seconds=60, microseconds=1)) is None


def test_a_longer_window_counts_for_longer():
    limiter = RateLimiter(timedelta(hours=1))
    limiter.check("someone@example.com", 1, NOW)
    assert limiter.check("someone@example.com", 1, NOW + timedelta(minutes=59)) is not None
    assert limiter.check("someone@example.com", 1, NOW + timedelta(minutes=61)) is None
