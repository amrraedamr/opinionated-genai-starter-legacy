from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from base import routers
from base.clients.redis_client import RedisClient
from base.middleware import (
    RequestBodyLimitMiddleware,
    RequestControlsMiddleware,
    SecurityHeadersMiddleware,
)
from base.models.view_models import ErrorResponse
from base.services.auth.dependencies import validate_user_dependency
from base.services.background_tasks.in_memory import InMemoryBackgroundTaskService
from base.services.common.meta import Stored, scope_id
from base.services.configuration import settings
from base.services.logging.console import ConsoleLoggerService
from base.services.logging.tee_stream import TerminalCaptureService
from base.services.prompt.loader import PromptLoader
from base.services.sql.service import SQLService
from base.tools.exception_handlers import AppExceptionHandler
from base.tools.routers import init_routers
from base.tools.stream import StreamIterator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger = ConsoleLoggerService()
    logger.info("Application starting")

    capture_service = TerminalCaptureService(settings.app_name)
    capture_service.start()

    try:
        await PromptLoader().initialize()
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        logger.info("Application shutting down")
        await PromptLoader().shutdown()
        await InMemoryBackgroundTaskService().ashutdown()
        await capture_service.stop()


app = FastAPI(lifespan=lifespan)
app.state.ready = False

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        host.strip()
        for host in settings.trusted_hosts.split(",")
        if host.strip()
    ],
)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(RequestControlsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.allowed_origins.split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def register_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_scope_id = _request_correlation_id(request)
    scope_id.set(request_scope_id)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = str(request_scope_id)
        return response
    finally:
        if response is None or not response.headers.get(
            "content-type", ""
        ).startswith("text/event-stream"):
            Stored.delete_scope(request_scope_id)


init_routers(
    app,
    routers=routers,
    prefix=settings.api_prefix,
)


AppExceptionHandler().register(app)


@app.get("/", tags=["Main"])
def root():
    return {
        "message": "Welcome to the Opinionated GenAI Starter API!",
        "version": "0.1",
    }


@app.get("/health-check", tags=["Main"])
def health_check():
    return {"status": "ok"}


@app.get("/livez", tags=["Main"])
def liveness_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["Main"])
async def readiness_check() -> Response:
    if not app.state.ready:
        return JSONResponse(
            content=ErrorResponse(error="Service is not ready.").serialize(
                exclude_none=True
            ),
            status_code=503,
        )
    try:
        await SQLService().ahealth_check()
        if settings.redis_url and not await RedisClient().aping():
            raise RuntimeError("Redis health check failed")
    except Exception:
        return JSONResponse(
            content=ErrorResponse(error="Dependencies are not ready.").serialize(
                exclude_none=True
            ),
            status_code=503,
        )
    return Response(
        content='{"status":"ok"}',
        status_code=200,
        media_type="application/json",
    )


@app.post(
    "/logs",
    dependencies=[validate_user_dependency],
)
async def get_logs():
    request_scope_id = scope_id.get()
    capture_service = TerminalCaptureService(settings.app_name)
    stream_iterator = StreamIterator(source=capture_service.subscribe())
    return EventSourceResponse(
        stream_iterator,
        media_type="text/event-stream",
        background=BackgroundTask(Stored.delete_scope, request_scope_id),
    )


def _request_correlation_id(request: Request) -> UUID:
    supplied = request.headers.get("x-correlation-id")
    if supplied:
        try:
            return UUID(supplied)
        except ValueError:
            pass
    traceparent = request.headers.get("traceparent", "")
    parts = traceparent.split("-")
    if len(parts) == 4 and len(parts[1]) == 32:
        try:
            return UUID(hex=parts[1])
        except ValueError:
            pass
    return uuid4()
