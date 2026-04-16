from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class SlidingWindowRateLimiter:
    """Simple in-memory per-IP limiter (suffisant pour une instance locale)."""

    def __init__(self, max_calls: int, window_seconds: float = 60.0) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        arr = self._hits[key]
        arr[:] = [t for t in arr if t > cutoff]
        if len(arr) >= self.max_calls:
            return False
        arr.append(now)
        return True


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Lit `get_settings()` à l’exécution pour rester cohérent avec les tests (`reset_settings_cache`)."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._limiter: SlidingWindowRateLimiter | None = None
        self._last_max: int = -1

    async def dispatch(self, request: Request, call_next):
        from app.config import get_settings

        s = get_settings()
        if not s.rate_limit_enabled:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if self._limiter is None or self._last_max != s.rate_limit_per_minute:
            self._limiter = SlidingWindowRateLimiter(max_calls=s.rate_limit_per_minute)
            self._last_max = s.rate_limit_per_minute
        key = _client_key(request)
        if not self._limiter.allow(key):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Trop de requêtes. Réessaie dans une minute ou augmente RATE_LIMIT_PER_MINUTE.",
                },
            )
        return await call_next(request)
