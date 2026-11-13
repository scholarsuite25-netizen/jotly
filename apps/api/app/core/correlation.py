from contextvars import ContextVar
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    cid = _correlation_id_ctx.get()
    if not cid:
        cid = str(uuid.uuid4())
        _correlation_id_ctx.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    _correlation_id_ctx.set(cid)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attaches a deterministic or generated X-Correlation-ID header to every request/response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("X-Correlation-ID", "").strip()
        correlation_id = incoming if incoming else str(uuid.uuid4())
        set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id

        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response
