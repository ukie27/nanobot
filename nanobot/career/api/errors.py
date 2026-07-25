"""RFC 9457-style Problem Details mappings."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from nanobot.career.api.middleware.correlation import correlation_id_context
from nanobot.career.domain.common.errors import CareerDomainError


def problem_response(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    code: str,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://nanobot.local/problems/{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "code": code,
        "correlationId": getattr(request.state, "correlation_id", None)
        or correlation_id_context.get(),
    }
    if extensions:
        body.update(extensions)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CareerDomainError)
    async def handle_domain_error(request: Request, exc: CareerDomainError) -> JSONResponse:
        return problem_response(
            request,
            status=exc.status_code,
            title="Career rule rejected the request",
            detail=exc.detail,
            code=exc.code,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
            for item in exc.errors()
        ]
        return problem_response(
            request,
            status=422,
            title="Request validation failed",
            detail="One or more request fields are invalid.",
            code="validation_error",
            extensions={"errors": errors},
        )

    @app.exception_handler(HTTPException)
    async def handle_http(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code") or "http_error")
            detail = str(
                exc.detail.get("message")
                or exc.detail.get("detail")
                or "The HTTP request failed."
            )
            extensions = {
                key: value
                for key, value in exc.detail.items()
                if key not in {"code", "message", "detail"}
            }
        else:
            code = "http_error"
            detail = str(exc.detail)
            extensions = {}
        return problem_response(
            request,
            status=exc.status_code,
            title="HTTP request failed",
            detail=detail,
            code=code,
            extensions=extensions or None,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.bind(correlation_id=correlation_id_context.get()).exception(
            "Unhandled Career API error: {}", type(exc).__name__
        )
        return problem_response(
            request,
            status=500,
            title="Internal server error",
            detail="The request could not be completed. Use the correlation ID for diagnosis.",
            code="internal_error",
        )
