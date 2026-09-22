"""A deliberately small in-memory rate limiter for the login endpoint.

Caveat: state lives in this process only. If you ever run more than one worker
or replica, move this to Redis. It is here so /authenticate is not a wide-open
brute force target during development.
"""

import time
from collections import defaultdict, deque

from app.core.config import settings

_attempts: dict[str, deque[float]] = defaultdict(deque)


def is_rate_limited(key: str) -> bool:
    """Record an attempt for `key`; return True if it exceeded the allowance."""
    window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    limit = settings.LOGIN_RATE_LIMIT_ATTEMPTS
    now = time.monotonic()

    bucket = _attempts[key]
    while bucket and now - bucket[0] > window:
        bucket.popleft()

    if len(bucket) >= limit:
        return True

    bucket.append(now)
    return False


def reset(key: str) -> None:
    """Clear the counter, e.g. after a successful login."""
    _attempts.pop(key, None)
