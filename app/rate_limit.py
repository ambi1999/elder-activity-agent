"""Per-device request limits for uploads (ADR 0020).

Each device may send ``ingest.batches_per_minute_per_device`` batches in any
60-second window; more get 429 Too Many Requests with a Retry-After header.
One faulty or stolen phone therefore can't overload the service, and other
phones are unaffected.

The counts are kept in memory, which is right for the single instance this
service runs as. With several instances each would count separately; a shared
store (for example Postgres or Redis) would then be needed.
"""

import math
import threading
from collections import deque
from datetime import datetime, timedelta

WINDOW = timedelta(minutes=1)


class RateLimiter:
    """Counts requests per key in a sliding one-minute window. Thread-safe."""

    def __init__(self) -> None:
        self._seen: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, now: datetime) -> int | None:
        """Record a request if it is allowed.

        Args:
            key: Who is making the request, e.g. the device ID.
            limit: Requests allowed per window.
            now: Current time, passed in so tests control the clock.

        Returns:
            None if the request is allowed (and counted); otherwise the whole
            number of seconds to wait before retrying.
        """
        with self._lock:
            times = self._seen.setdefault(key, deque())
            while times and times[0] <= now - WINDOW:
                times.popleft()
            if len(times) >= limit:
                wait = (times[0] + WINDOW - now).total_seconds()
                return max(1, math.ceil(wait))
            times.append(now)
            return None

    def reset(self) -> None:
        """Forget all counts (used by tests)."""
        with self._lock:
            self._seen.clear()


# One limiter for uploads, shared by all requests in this process.
uploads = RateLimiter()
