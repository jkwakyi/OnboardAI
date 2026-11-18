"""Limiting repeated failures in front of a route (ON-37).

Recorded as TD-20 when the Auth Service landed: scrypt makes a password
guess expensive rather than free, but expensive is not prevented, and the
same cost is also a way to make the server do a quarter of a second of work
per request. Both halves of that want the same thing - a limit that is
checked *before* any hashing happens.

A sliding window of failure times per key. Not a token bucket: the useful
question here is "how many failures in the last fifteen minutes", and a
window answers it directly and can say how long until the oldest failure
falls out, which is what Retry-After needs.

In process, so per worker
-------------------------
The count lives in this process's memory. Two uvicorn workers each allow
the full number, and a restart forgets everything. That is honest for the
alpha; the shape of the fix is the same code against Redis, which is a
change to ask about rather than to make quietly.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable


class TooManyAttempts(Exception):
    """The caller has failed too often and is being asked to wait."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"too many attempts; retry in {retry_after_seconds} seconds")
        self.retry_after_seconds = retry_after_seconds


class AttemptLimiter:
    """How many failures a key is allowed inside a moving window.

    `max_keys` is not a detail. Without it, an attacker who varies the
    address on every request makes this dictionary grow for as long as they
    keep going, and the thing protecting the login becomes the way to
    exhaust the server's memory. The least-recently-touched key is dropped
    instead, which is the right one to lose: a key at the front of the
    queue is one nobody has failed against recently.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        max_keys: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError(f"limit must be at least 1, not {limit}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, not {window_seconds}")
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        # A monotonic clock, so changing the system time cannot widen the
        # window or make every recorded failure look like it was in the
        # future.
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        # Sync endpoints run in a threadpool, so two requests really can be
        # in here at once.
        self._lock = threading.Lock()

    def _prune(self, times: deque[float], now: float) -> None:
        cutoff = now - self._window
        while times and times[0] <= cutoff:
            times.popleft()

    def check(self, key: str) -> None:
        """Raise TooManyAttempts if this key has used up its allowance."""
        with self._lock:
            times = self._failures.get(key)
            if times is None:
                return
            now = self._clock()
            self._prune(times, now)
            if not times:
                del self._failures[key]
                return
            if len(times) >= self._limit:
                # Until the oldest failure leaves the window. Rounded up,
                # because a Retry-After of 0 invites an immediate retry
                # that is still refused.
                wait = self._window - (now - times[0])
                raise TooManyAttempts(max(1, int(wait) + 1))

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            times = self._failures.get(key)
            if times is None:
                times = deque()
                self._failures[key] = times
            self._prune(times, now)
            times.append(now)
            self._failures.move_to_end(key)
            while len(self._failures) > self._max_keys:
                self._failures.popitem(last=False)

    def clear(self, key: str) -> None:
        """Forget this key's failures. Called when it succeeds."""
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        """Forget everything. For tests and for a fresh application."""
        with self._lock:
            self._failures.clear()

    @property
    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._failures)


__all__ = ["AttemptLimiter", "TooManyAttempts"]
