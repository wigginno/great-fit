"""FastAPI middleware to attach a unique X-Request-ID header to every request
and bind it into structlog contextvars so that all log lines contain the same
request_id for correlation across services and SSE events.
"""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Use structlog contextvars helpers. _bind binds for this context, _clear at end.
from structlog.contextvars import bind_contextvars, clear_contextvars


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a short UUID4 request_id to each incoming request.

    The ID is returned in the "X-Request-ID" response header and bound into
    structlog contextvars so that every log line generated while the request
    is processing automatically includes the request_id field.
    """

    def __init__(self, app, header_name: str = "X-Request-ID") -> None:  # type: ignore[override]
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:  # noqa: D401,E501  # type: ignore[override]
        # Generate a UUID4 without hyphens for brevity
        request_id = uuid.uuid4().hex
        # Bind to structlog so every log line in this request includes it
        bind_contextvars(request_id=request_id)
        # Expose also on request.state for easy access further down the stack
        request.state.request_id = request_id

        # Proceed with the request
        try:
            response: Response = await call_next(request)
        finally:
            # Always clear contextvars to avoid leaking to other requests (esp. in async)
            clear_contextvars()

        # Add header so clients/services can correlate
        response.headers[self.header_name] = request_id
        return response
