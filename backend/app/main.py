"""FastAPI application."""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    admin_evals,
    admin_insights,
    admin_jobs,
    admin_team,
    auth,
    chat,
    health,
    profile,
    search,
    student,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, request_id_var
from app.core.metrics import metrics

logger = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


def _error(status: int, code: str, message: str, details: object = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details}}
    body["error"]["request_id"] = request_id_var.get()
    return JSONResponse(body, status_code=status)


def _friendly_validation(exc: RequestValidationError) -> list[dict[str, str]]:
    fields = []
    for err in exc.errors():
        location = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        message = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        fields.append({"field": ".".join(location), "message": message})
    return fields


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="placement_rag",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
            if request.url.path.startswith("/api"):
                response.headers.setdefault("Cache-Control", "no-store")
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = getattr(request.scope.get("route"), "path", "unmatched")
            metrics.observe(request.method, route, status, elapsed)
            if not route.startswith(("/healthz", "/readyz")):
                logger.info(
                    "request",
                    extra={
                        "method": request.method,
                        "route": route,
                        "status": status,
                        "ms": round(elapsed * 1000, 1),
                    },
                )
            request_id_var.reset(token)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = _friendly_validation(exc)
        return _error(422, "invalid_input", "Some fields need your attention.", fields)

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled", exc_info=exc)
        return _error(
            500, "server_error", "Something went wrong on our side. Please try again in a moment."
        )

    modules = (
        health,
        auth,
        admin_team,
        admin_jobs,
        admin_insights,
        admin_evals,
        search,
        profile,
        student,
        chat,
    )
    for module in modules:
        app.include_router(module.router)
    return app


app = create_app()
