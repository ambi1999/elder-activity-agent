"""Reject oversized request bodies before they are read into memory (ADR 0020).

The limit is ``ingest.max_body_bytes``. Too-large requests get 413 as Problem
Details, the format protocol v1 uses; other clients only look at the status.
"""

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.problems import problem_response


class BodyTooLarge(HTTPException):
    """The body grew past the limit while it was being received.

    An HTTPException, because FastAPI passes those through unchanged when it
    reads a route's body (other errors become 400). Routes that read the body
    themselves, such as /v1/readings, catch it and answer with Problem Details.
    """

    def __init__(self) -> None:
        super().__init__(status_code=413, detail="Request body too large")


class MaxBodySizeMiddleware:
    """ASGI middleware that refuses request bodies larger than ``max_bytes``.

    Args:
        app: The application to wrap.
        max_bytes: Largest body allowed, in bytes.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI request, refusing it if its body is too large."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        too_large = problem_response(413, f"Request body larger than {self.max_bytes} bytes; send smaller batches.")

        # Fast path: the client declared the size up front.
        for name, value in scope["headers"]:
            if name == b"content-length" and value.isdigit() and int(value) > self.max_bytes:
                await too_large(scope, receive, send)
                return

        # Otherwise count bytes as they arrive and stop once over the limit.
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLarge
            return message

        await self.app(scope, limited_receive, send)
