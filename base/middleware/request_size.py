from typing import Any

from fastapi import Request

from base.middleware.responses import _error_response
from base.services.configuration import settings


class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                body_size = int(content_length)
            except ValueError:
                await _error_response(
                    Request(scope, receive),
                    "Invalid Content-Length.",
                    400,
                )(scope, receive, send)
                return
            if body_size > settings.max_request_body_bytes:
                await _error_response(
                    Request(scope, receive),
                    "Request body is too large.",
                    413,
                )(scope, receive, send)
                return

        total = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > settings.max_request_body_bytes:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await _error_response(
                Request(scope, receive),
                "Request body is too large.",
                413,
            )(scope, receive, send)
