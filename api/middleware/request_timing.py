"""Middleware: tempo total da requisição (útil vs TTFB no cliente)."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("map_engine.request")


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        total_ms = int((time.perf_counter() - t0) * 1000)
        log.info(
            "request_total method=%s path=%s status=%s total_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            total_ms,
        )
        response.headers["X-Request-Time-Ms"] = str(total_ms)
        return response
