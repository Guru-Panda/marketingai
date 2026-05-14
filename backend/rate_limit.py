import time
import threading
from collections import defaultdict

from fastapi import HTTPException

_lock = threading.Lock()
_hits: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, max_calls: int, window_seconds: int) -> None:
    """Raise HTTP 429 if `key` has exceeded `max_calls` within `window_seconds`."""
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        bucket = _hits[key]
        # Drop expired entries from the front
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait and try again.",
            )
        bucket.append(now)
