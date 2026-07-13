"""Consistent error responses (roadmap §10.5).

Every non-success body is {code, message, fieldErrors?, requestId}. Internal
errors never leak paths, stack traces, raw content, tokens, or key material.
"""

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 field_errors: dict[str, str] | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.field_errors = field_errors


def _body(code: str, message: str, field_errors: dict[str, str] | None = None) -> dict:
    body = {"code": code, "message": message, "requestId": uuid.uuid4().hex[:12]}
    if field_errors:
        body["fieldErrors"] = field_errors
    return body


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message, exc.field_errors))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # §10.5: a body that is not valid JSON at all is a malformed request
        # (400); a well-formed body with bad values is a validation error (422).
        if any(err.get("type") == "json_invalid" for err in exc.errors()):
            return JSONResponse(status_code=400, content=_body(
                "bad_request", "The request body is not valid JSON."))
        field_errors = {}
        for err in exc.errors():
            loc = [str(part) for part in err.get("loc", []) if part not in ("body", "query", "path")]
            field_errors[".".join(loc) or "request"] = err.get("msg", "Invalid value.")
        return JSONResponse(status_code=422, content=_body(
            "validation_error", "The request could not be processed.", field_errors))

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found",
                405: "method_not_allowed", 413: "payload_too_large",
                429: "rate_limited"}.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else "The request failed."
        return JSONResponse(status_code=exc.status_code, content=_body(code, message))

    @app.exception_handler(Exception)
    async def fallback_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content=_body(
            "internal_error", "An internal error occurred."))
