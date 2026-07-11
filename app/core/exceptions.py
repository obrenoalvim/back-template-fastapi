from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class ApiException(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: list[str] | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def not_found(message: str = "Not found") -> ApiException:
    return ApiException(status.HTTP_404_NOT_FOUND, "NOT_FOUND", message)


def unauthorized(message: str = "Authentication required") -> ApiException:
    return ApiException(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", message)


def forbidden(message: str = "Insufficient role") -> ApiException:
    return ApiException(status.HTTP_403_FORBIDDEN, "FORBIDDEN", message)


def conflict(message: str) -> ApiException:
    return ApiException(status.HTTP_409_CONFLICT, "CONFLICT", message)


def _error_body(code: str, message: str, details: list[str] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiException)
    async def api_exception_handler(_: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_body("VALIDATION_ERROR", "Invalid request body", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "RATE_LIMITED" if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS else "HTTP_ERROR"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("INTERNAL_ERROR", "Unexpected error"),
        )
