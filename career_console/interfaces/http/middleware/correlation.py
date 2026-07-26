"""Correlation IDs for API responses and structured logs."""

from __future__ import annotations

import re
from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("X-Correlation-ID", "")
        correlation_id = supplied if _SAFE_ID.fullmatch(supplied) else str(uuid4())
        token = correlation_id_context.set(correlation_id)
        request.state.correlation_id = correlation_id
        bound = logger.bind(correlation_id=correlation_id)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            bound.info(
                "HTTP request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )
            return response
        finally:
            correlation_id_context.reset(token)
