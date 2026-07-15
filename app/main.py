"""FastAPI application factory.

This module creates and configures the FastAPI application instance.
Routers, middleware, startup/shutdown lifecycle, and global exception
handlers are all registered here.  Business logic must never live in
this file.

Startup sequence (lifespan):
    1. Configure structured logging (must be first)
    2. Initialise SQLite/PostgreSQL engine (``init_db``)
    3. Initialise MongoDB client (``init_mongo``)
    4. Create MongoDB indexes (``ensure_indexes``)
    5. Log ready message

Shutdown sequence (lifespan):
    1. Close MongoDB client (``close_mongo``)
    2. Dispose database engine (``close_db``)
    3. Log goodbye message

Run locally (no Docker required)::

    uvicorn app.main:app --reload

Run via Docker Compose::

    docker compose up
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.constants import HEADER_REQUEST_ID
from app.core.logging import configure_logging, get_logger, set_request_id
from app.infrastructure.database import check_db_health, close_db, init_db
from app.infrastructure.mongodb import (
    check_mongo_health,
    close_mongo,
    ensure_indexes,
    init_mongo,
)

logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown in a single coroutine.

    Using ``asynccontextmanager`` (FastAPI lifespan) instead of the
    deprecated ``@app.on_event`` handlers ensures startup/shutdown
    are always a matched pair, even if startup raises an exception.
    """
    settings: Settings = get_settings()

    # 1. Configure logging first — all subsequent log calls benefit from it
    configure_logging(
        log_level=settings.log_level,
        is_development=settings.is_development,
    )

    logger.info(
        "Starting DocTrace AI",
        version=settings.app_version,
        environment=settings.environment,
        database=settings.database_url.split("///")[-1] if settings.is_sqlite else "external",
        llm_model=settings.llm_model,
    )

    # 2. Initialise relational database
    await init_db(settings)

    # 3. Initialise MongoDB (non-fatal if unavailable)
    try:
        await init_mongo(settings)
        await ensure_indexes()
    except Exception as exc:
        # MongoDB failure is non-fatal at startup — LLM endpoints will
        # return 503 until connectivity is established.
        logger.warning(
            "MongoDB initialisation failed at startup — "
            "LLM generation endpoints will be unavailable until resolved.",
            error=str(exc),
        )

    logger.info("DocTrace AI is ready to serve requests")

    yield  # ← application runs here

    # Shutdown: reverse order of initialisation
    await close_mongo()
    await close_db()

    logger.info("DocTrace AI shutdown complete")


# ── Application factory ───────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Separating creation from the module-level ``app`` variable allows tests
    to call ``create_app()`` with isolated state without side effects.

    Returns:
        A fully configured ``FastAPI`` instance.
    """
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI-powered document tracing backend.  "
            "Upload PDFs, version them, select node ranges, "
            "and generate structured QA test cases with an LLM."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    _register_middleware(application, settings)
    _register_exception_handlers(application)
    _register_routes(application)

    return application


# ── Middleware ────────────────────────────────────────────────────────────────


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    """Register all middleware in LIFO order (last registered = outermost)."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[HEADER_REQUEST_ID],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Response:
        """Inject a per-request correlation ID and log request completion.

        Reads ``X-Request-ID`` from the incoming request if present;
        generates a new UUID4 otherwise.  The ID is:
            - Bound to the async context (visible in all log lines)
            - Written to the response ``X-Request-ID`` header
        """
        incoming_id = request.headers.get(HEADER_REQUEST_ID)
        request_id = set_request_id(incoming_id)

        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1_000, 2)

        response.headers[HEADER_REQUEST_ID] = request_id

        logger.info(
            "HTTP",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response


# ── Exception handlers ────────────────────────────────────────────────────────


def _register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers.

    The catch-all handler prevents raw Python tracebacks from reaching
    API consumers.  Domain-specific handlers are added in M11.
    """

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Return a structured 500 response for all unhandled exceptions."""
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
                "request_id": request.headers.get(HEADER_REQUEST_ID, ""),
            },
        )


# ── Routes ────────────────────────────────────────────────────────────────────


def _register_routes(app: FastAPI) -> None:
    """Register all API routes.

    V1 routers are registered in M11.  The health endpoints are always
    present, including before the database is ready.
    """

    @app.get(
        "/health",
        tags=["Health"],
        summary="Liveness check",
        description=(
            "Returns 200 OK when the application process is running.  "
            "Does **not** verify database or MongoDB connectivity.  "
            "Use ``/health/ready`` for a full readiness check."
        ),
    )
    async def health_check() -> dict[str, str]:
        """Return basic process liveness status."""
        return {"status": "healthy"}

    @app.get(
        "/health/ready",
        tags=["Health"],
        summary="Readiness check",
        description=(
            "Returns 200 OK when the application **and all its dependencies** "
            "are ready to serve traffic.  "
            "Returns 503 if the database or MongoDB are unreachable.  "
            "Suitable for Kubernetes readiness probes."
        ),
    )
    async def readiness_check() -> dict[str, Any]:
        """Verify connectivity to all required external services."""
        db_ok = await check_db_health()
        mongo_ok = await check_mongo_health()

        services: dict[str, str] = {
            "database": "healthy" if db_ok else "unhealthy",
            "mongodb": "healthy" if mongo_ok else "unhealthy",
        }

        if not db_ok:
            # Database is hard-required; MongoDB degradation is tolerated
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "unavailable",
                    "message": "One or more required services are unreachable.",
                    "services": services,
                },
            )

        return {
            "status": "ready",
            "services": services,
        }

    # ── V1 API routers (registered in M11) ───────────────────────────────────
    # from app.core.constants import API_V1_PREFIX
    # from app.api.v1 import documents, versions, nodes, selections, generations
    # app.include_router(documents.router, prefix=API_V1_PREFIX)
    # app.include_router(versions.router, prefix=API_V1_PREFIX)
    # app.include_router(nodes.router, prefix=API_V1_PREFIX)
    # app.include_router(selections.router, prefix=API_V1_PREFIX)
    # app.include_router(generations.router, prefix=API_V1_PREFIX)


# ── Module-level app instance ─────────────────────────────────────────────────

app = create_app()
