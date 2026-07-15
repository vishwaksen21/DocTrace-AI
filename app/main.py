"""FastAPI application factory.

This module creates and configures the FastAPI application instance.
Routers, middleware, startup/shutdown lifecycle, and global exception
handlers are registered here.

Business logic must never be placed in this file.  Route handlers
are in ``app/api/v1/`` and delegate all work to the service layer.

Usage
-----
Run locally::

    uvicorn app.main:app --reload

Or via Docker::

    docker compose up app
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.infrastructure.logging import (
    configure_logging,
    get_logger,
    set_request_id,
)

logger = get_logger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown events.

    Startup sequence:
        1. Configure structured logging (must be first)
        2. Initialize PostgreSQL connection pool
        3. Initialize MongoDB connection
        4. Log ready message

    Shutdown sequence:
        1. Close PostgreSQL connection pool
        2. Close MongoDB connection
        3. Log goodbye message

    Database initialisation is deferred to Module 2 (M2).
    The lifespan hook is already wired so M2 only needs to import and call
    the relevant infrastructure functions.
    """
    settings: Settings = get_settings()

    # Step 1 — logging must be configured before any other startup work
    configure_logging(
        log_level=settings.log_level,
        is_development=settings.is_development,
    )

    logger.info(
        "Starting up DocTrace AI",
        version=settings.app_version,
        environment=settings.environment,
        llm_model=settings.llm_model,
        llm_base_url=settings.openrouter_base_url,
    )

    # ── Future startup hooks (added in subsequent modules) ────────────────────
    # from app.infrastructure.database import init_db, close_db   # M2
    # from app.infrastructure.mongodb import init_mongo, close_mongo  # M2
    # await init_db()
    # await init_mongo()
    # ─────────────────────────────────────────────────────────────────────────

    logger.info("DocTrace AI is ready")

    yield  # Application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down DocTrace AI")

    # await close_db()    # M2
    # await close_mongo() # M2


# ── Application factory ───────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    This factory function is separated from the module-level ``app`` variable
    to make the application testable: tests can call ``create_app()`` with
    different configurations without side effects.

    Returns:
        A fully configured ``FastAPI`` instance.
    """
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI-powered document tracing backend.  "
            "Upload PDF documents, version them, select node ranges, "
            "and generate structured QA test cases using an LLM."
        ),
        # Swagger UI and ReDoc are only available in non-production environments.
        # In production, disable interactive docs to reduce attack surface.
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    _register_middleware(application, settings)
    _register_exception_handlers(application)
    _register_routes(application)

    return application


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    """Register all FastAPI middleware in the correct order.

    Middleware is applied in LIFO order (last added = outermost).  The
    request-ID middleware is added last so it runs first (outermost position),
    ensuring all inner middleware and handlers have a correlation ID available.
    """
    # CORS — permissive for development; tighten via config for production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: restrict via settings.allowed_origins in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Response:
        """Inject a correlation ID into every request.

        Reads ``X-Request-ID`` from the incoming request header if present;
        otherwise generates a new UUID4.  The ID is:
          - Bound to the current async context via ``set_request_id``
          - Included in the response header for client-side tracing
          - Automatically added to every log line within this request
        """
        incoming_id = request.headers.get("X-Request-ID")
        request_id = set_request_id(incoming_id)

        start_time = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)

        response.headers["X-Request-ID"] = request_id

        logger.info(
            "HTTP request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response


def _register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers.

    Detailed domain-specific handlers are added in M11 (API layer).
    This registers only a catch-all for unexpected exceptions.
    """

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Return a structured error response for all unhandled exceptions.

        This prevents raw Python tracebacks from leaking to API consumers.
        The full exception is logged server-side with exc_info for debugging.
        """
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred.  Please try again.",
                "request_id": request.headers.get("X-Request-ID", ""),
            },
        )


def _register_routes(app: FastAPI) -> None:
    """Register all API routers.

    Routers are registered here once the API layer is implemented (M11).
    The health check endpoint is registered directly on the app since it
    must be available at all times, including before the DB is ready.
    """

    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check",
        description=(
            "Returns the application's health status.  "
            "Returns 200 OK when the service is running.  "
            "Does **not** verify database connectivity (see /health/ready for that)."
        ),
        response_description="Application health status",
    )
    async def health_check() -> dict[str, str]:
        """Return basic liveness status."""
        settings = get_settings()
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
        }

    # ── Future router registrations (M11) ─────────────────────────────────────
    # from app.api.v1 import documents, versions, nodes, selections, generations
    # API_PREFIX = "/api/v1"
    # app.include_router(documents.router, prefix=API_PREFIX)
    # app.include_router(versions.router, prefix=API_PREFIX)
    # app.include_router(nodes.router, prefix=API_PREFIX)
    # app.include_router(selections.router, prefix=API_PREFIX)
    # app.include_router(generations.router, prefix=API_PREFIX)


# ── Module-level app instance ─────────────────────────────────────────────────
#
# This is what uvicorn references: ``uvicorn app.main:app``
# Tests that need isolation should call ``create_app()`` directly.

app = create_app()
