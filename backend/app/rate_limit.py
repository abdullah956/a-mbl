"""Tiny in-memory sliding-window rate limiter for the local prototype."""

import time
from collections import defaultdict, deque

from .errors import ApiError

_events: dict[str, deque] = defaultdict(deque)

# Every key (one per email / user / action) would otherwise live for the whole
# process; idle keys are swept out periodically so memory stays bounded.
_SWEEP_EVERY = 1_000
_IDLE_SECONDS = 3_600
_calls = 0


def _sweep(now: float) -> None:
    idle = [key for key, window in _events.items()
            if not window or window[-1] <= now - _IDLE_SECONDS]
    for key in idle:
        del _events[key]


def check(key: str, limit: int, per_seconds: int = 60) -> None:
    global _calls
    now = time.monotonic()
    _calls += 1
    if _calls % _SWEEP_EVERY == 0:
        _sweep(now)
    window = _events[key]
    while window and window[0] <= now - per_seconds:
        window.popleft()
    if len(window) >= limit:
        raise ApiError(429, "rate_limited", "Too many requests. Please wait a moment and try again.")
    window.append(now)


def reset() -> None:
    _events.clear()
