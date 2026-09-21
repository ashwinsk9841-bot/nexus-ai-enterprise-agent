"""In-memory sliding-window rate limiter (per process)."""

import threading
import time
from collections import defaultdict, deque

from ..core.config import settings


class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = defaultdict(deque)

    def _cleanup(self, key: str, window_seconds: float):
        now = time.monotonic()
        q = self._hits[key]
        while q and q[0] < now - window_seconds:
            q.popleft()

    def allow(self, key: str, max_requests: int, window_seconds: float) -> bool:
        with self._lock:
            self._cleanup(key, window_seconds)
            if max_requests <= 0:
                return True
            if len(self._hits[key]) >= max_requests:
                return False
            self._hits[key].append(time.monotonic())
            return True

    def is_limited(self, key: str, max_requests: int, window_seconds: float) -> bool:
        with self._lock:
            self._cleanup(key, window_seconds)
            if max_requests <= 0:
                return False
            return len(self._hits[key]) >= max_requests

    def reset(self, key: str):
        with self._lock:
            self._hits.pop(key, None)

    def clear(self):
        with self._lock:
            self._hits.clear()


_limiter = RateLimiter()


def is_login_rate_limited(ip: str, scope: str = "") -> bool:
    """Check whether login is currently blocked without recording an attempt."""
    return _limiter.is_limited(
        f"login:{ip}:{scope}",
        settings.LOGIN_MAX_ATTEMPTS,
        settings.LOGIN_WINDOW_MINUTES * 60,
    )


def limit_login(ip: str, scope: str = "") -> bool:
    """Per-IP + per-account login throttle (sliding window). Records an attempt."""
    return _limiter.allow(
        f"login:{ip}:{scope}",
        settings.LOGIN_MAX_ATTEMPTS,
        settings.LOGIN_WINDOW_MINUTES * 60,
    )


def clear_login(ip: str, scope: str = "") -> None:
    """Clear the login failure throttle for an IP + account (e.g. after a successful login)."""
    _limiter.reset(f"login:{ip}:{scope}")


def limit_generic(key: str, max_requests: int = 10, window_seconds: float = 300) -> bool:
    """Generic rate limit for registration and other high-volume endpoints."""
    return _limiter.allow(key, max_requests, window_seconds)