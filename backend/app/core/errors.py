"""
Consistent API error handling.

All unhandled exceptions are converted into a single JSON envelope so the
frontend can rely on one error shape regardless of endpoint. Internal
details (stack traces, exception messages) are logged server-side only and
never sent to the client.
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("bis_sahayak")


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # A route may raise HTTPException(detail={"code": "...", "message": "..."})
        # to surface a specific error code (e.g. LLM_NOT_CONFIGURED) instead
        # of the generic HTTP-status-as-code fallback below.
        if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=_error_body(**exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code=str(exc.status_code), message=str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body(code="validation_error", message="Request validation failed."),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Full details go to the local developer log only.
        logger.exception("Unhandled exception while processing %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_error_body(code="internal_error", message="An unexpected error occurred."),
        )
