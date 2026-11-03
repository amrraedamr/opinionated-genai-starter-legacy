import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from base.models.view_models import ErrorResponse
from base.services.configuration import settings


@dataclass
class _ClientState:
    requests: deque[float] = field(default_factory=deque)
    active: int = 0
    last_seen: float = 0


class RequestControlsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._clients: dict[str, _ClientState] = {}
        self._lock = asyncio.Lock()

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client_key = self._client_key(scope)
        now = time.monotonic()
        async with self._lock:
            self._evict_idle(now)
            state = self._clients.setdefault(client_key, _ClientState())
            cutoff = now - settings.rate_limit_window_seconds
            while state.requests and state.requests[0] <= cutoff:
                state.requests.popleft()
            if len(state.requests) >= settings.rate_limit_requests:
                await self._reject(scope, receive, send, "Rate limit exceeded.")
                return
            if state.active >= settings.max_concurrent_requests_per_client:
                await self._reject(
                    scope, receive, send, "Too many concurrent requests."
                )
                return
            state.requests.append(now)
            state.active += 1
            state.last_seen = now

        try:
            await self.app(scope, receive, send)
        finally:
            async with self._lock:
                state = self._clients.get(client_key)
                if state is not None:
                    state.active = max(state.active - 1, 0)
                    state.last_seen = time.monotonic()

    @staticmethod
    def _client_key(scope: Scope) -> str:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if settings.trust_proxy_headers:
            forwarded = headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",", 1)[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _evict_idle(self, now: float) -> None:
        cutoff = now - settings.rate_limit_window_seconds
        for key, state in list(self._clients.items()):
            while state.requests and state.requests[0] <= cutoff:
                state.requests.popleft()
            if state.active == 0 and not state.requests:
                self._clients.pop(key, None)

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        message: str,
    ) -> None:
        response = JSONResponse(
            content=ErrorResponse(error=message).serialize(exclude_none=True),
            status_code=429,
            headers={"Retry-After": "1"},
        )
        await response(scope, receive, send)
