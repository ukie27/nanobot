"""Loopback browser-session, CSRF, and response-header protections."""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class LocalBrowserSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str, allowed_origins: set[str]) -> None:
        super().__init__(app)
        self._token = token
        self._allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin")
        if origin and origin not in self._allowed_origins:
            return JSONResponse(
                {"code": "origin_not_allowed", "detail": "Browser origin is not allowed."},
                status_code=403,
            )
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/api/v1/system/session"
        ):
            cookie = request.cookies.get("career_session", "")
            header = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(cookie, self._token) or not hmac.compare_digest(
                header, self._token
            ):
                return JSONResponse(
                    {"code": "csrf_validation_failed", "detail": "Local browser session is invalid."},
                    status_code=403,
                )
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self' http://127.0.0.1:5173 http://localhost:5173; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
