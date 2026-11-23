"""Errors as Problem Details (RFC 9457), as protocol v1 requires for /v1 routes.

A route raises ``Problem``; the handler registered in ``app.main`` turns it into
a response with ``Content-Type: application/problem+json``:

    {"type": "about:blank", "title": "Too Many Requests", "status": 429, "detail": "..."}
"""

from http import HTTPStatus

from starlette.requests import Request
from starlette.responses import JSONResponse

MEDIA_TYPE = "application/problem+json"


class Problem(Exception):
    """An error to return to the client as Problem Details.

    Args:
        status: HTTP status code.
        detail: What went wrong, for the person reading the phone's logs. Never
            include tokens or sensor values.
        headers: Extra response headers, such as Retry-After.
    """

    def __init__(self, status: int, detail: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.headers = headers or {}


def problem_response(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    """A Problem Details response. Also used by middleware, outside any route."""
    body = {"type": "about:blank", "title": HTTPStatus(status).phrase, "status": status, "detail": detail}
    return JSONResponse(body, status_code=status, headers=headers, media_type=MEDIA_TYPE)


async def handle_problem(request: Request, exc: Exception) -> JSONResponse:
    """Exception handler for ``Problem``, registered on the FastAPI app."""
    assert isinstance(exc, Problem)  # noqa: S101 - FastAPI only routes Problem here
    return problem_response(exc.status, exc.detail, exc.headers)
