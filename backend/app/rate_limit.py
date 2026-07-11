"""Tiny in-memory sliding-window rate limiter for the local prototype."""

import time
from collections import defaultdict, deque

from .errors import ApiError

_events: dict[str, deque] = defaultdict(deque)


def check(key: str, limit: int, per_seconds: int = 60) -> None:
    now = time.monotonic()
    window = _events[key]
    while window and window[0] <= now - per_seconds:
        window.popleft()
    if len(window) >= limit:
        raise ApiError(429, "rate_limited", "Too many requests. Please wait a moment and try again.")
    window.append(now)


def reset() -> None:
    _events.clear()
