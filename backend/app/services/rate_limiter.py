import time
from collections import defaultdict, deque
from threading import Lock
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.config import get_settings


class SlidingWindowRateLimiter(BaseHTTPMiddleware):
    """Lightweight sliding-window rate limiter for API protection."""

    def __init__(self, app, max_requests_per_minute: int | None = None):
        super().__init__(app)
        self.max_requests = max_requests_per_minute or get_settings().rate_limit_requests_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Only rate-limit API/protocol endpoints, not static frontend assets
        if not (path.startswith("/api/") or path.startswith("/v1/")):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - 60.0

        with self._lock:
            q = self._hits[client_ip]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Retry after 60 seconds."},
                    headers={"Retry-After": "60"},
                )
            q.append(now)

        return await call_next(request)
