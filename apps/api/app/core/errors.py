from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.core.correlation import get_correlation_id


class NexusAPIError(Exception):
    """Domain/API error with safe error code and HTTP status."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NexusAPIError)
    async def handle_nexus_error(request: Request, exc: NexusAPIError) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", None) or get_correlation_id()
        return JSONResponse(
            status_code=exc.status_code,
            headers={"X-Correlation-ID": cid},
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "correlation_id": cid,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", None) or get_correlation_id()
        return JSONResponse(
            status_code=422,
            headers={"X-Correlation-ID": cid},
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request payload validation failed.",
                    "details": exc.errors(),
                    "correlation_id": cid,
                }
            },
        )
