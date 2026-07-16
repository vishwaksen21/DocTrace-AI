"""Observability setup: Prometheus metrics and OpenTelemetry tracing.

This module provides:
- Prometheus metrics endpoint at /metrics
- OpenTelemetry tracing with OTLP export
- FastAPI, SQLAlchemy, and httpx instrumentation
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

if TYPE_CHECKING:
    from app.core.config import Settings

# ── Prometheus Metrics ────────────────────────────────────────────────────────

# Registry for custom metrics (avoids global registry conflicts in tests)
registry = CollectorRegistry()

# HTTP request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

# Database metrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query latency in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=registry,
)

db_active_connections = Gauge(
    "db_active_connections",
    "Number of active database connections",
    registry=registry,
)

# LLM metrics
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["model", "status"],
    registry=registry,
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request latency in seconds",
    ["model"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=registry,
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens used",
    ["model", "type"],
    registry=registry,
)

# PDF parsing metrics
pdf_parse_duration_seconds = Histogram(
    "pdf_parse_duration_seconds",
    "PDF parsing latency in seconds",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=registry,
)

pdf_parse_pages = Histogram(
    "pdf_parse_pages",
    "Number of pages in parsed PDF",
    buckets=(1, 2, 5, 10, 25, 50, 100, 250, 500, 1000),
    registry=registry,
)

# Document/Version metrics
documents_total = Gauge(
    "documents_total",
    "Total number of documents",
    registry=registry,
)

versions_total = Gauge(
    "versions_total",
    "Total number of document versions",
    registry=registry,
)

nodes_total = Gauge(
    "nodes_total",
    "Total number of parsed nodes across all versions",
    registry=registry,
)

# ── Metrics Endpoint ──────────────────────────────────────────────────────────


async def metrics_endpoint() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
    )


# ── OpenTelemetry Tracing ─────────────────────────────────────────────────────


def init_tracing(settings: Settings) -> None:
    """Initialize OpenTelemetry tracing with OTLP exporter.

    Called once at startup. If OTEL is disabled, this is a no-op.
    """
    if not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.app_version,
            "deployment.environment": settings.environment,
        }
    )

    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_endpoint,
        insecure=settings.otel_exporter_insecure,
    )

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    logging.getLogger(__name__).info(
        "OpenTelemetry tracing initialized: service=%s endpoint=%s",
        settings.otel_service_name,
        settings.otel_exporter_endpoint,
    )


def instrument_app(app: FastAPI, settings: Settings) -> None:
    """Instrument FastAPI app with OpenTelemetry."""
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(
        engine=None,  # Will be set when engine is created
    )
    HTTPXClientInstrumentor().instrument()

    logging.getLogger(__name__).info("OpenTelemetry instrumentation applied")


def instrument_sqlalchemy_engine(engine: Any) -> None:
    """Instrument SQLAlchemy engine after creation."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(engine=engine)


# ── Lifespan Integration ──────────────────────────────────────────────────────


def create_observability_lifespan(settings: Settings
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Create a lifespan context manager for observability setup/teardown."""
    from app.auth import close_rate_limiter, init_rate_limiter
    from app.core.logging import configure_logging
    from app.infrastructure.database import close_db, init_db
    from app.infrastructure.mongodb import close_mongo, ensure_indexes, init_mongo

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # 1. Configure logging first — all subsequent log calls benefit from it
        configure_logging(
            log_level=settings.log_level,
            is_development=settings.is_development,
        )

        from app.core.logging import get_logger
        logger = get_logger(__name__)

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

        # 4. Initialize Redis for rate limiting
        await init_rate_limiter()

        # 5. Initialize observability (tracing, metrics)
        init_tracing(settings)
        instrument_app(app, settings)

        # Initialize metrics with current state
        from app.infrastructure.database import _engine

        if _engine is not None:
            instrument_sqlalchemy_engine(_engine)

        logger.info("DocTrace AI is ready to serve requests")

        yield

        # Shutdown: reverse order of initialisation
        await close_rate_limiter()
        await close_mongo()
        await close_db()

        # Shutdown - flush any pending spans
        if settings.otel_enabled:
            from opentelemetry import trace

            provider = trace.get_tracer_provider()
            if hasattr(provider, "shutdown"):
                provider.shutdown()

        logger.info("DocTrace AI shutdown complete")

    return _lifespan


# ── Utility Functions ─────────────────────────────────────────────────────────


def record_http_request(method: str, path: str, status: int, duration: float) -> None:
    """Record HTTP request metrics."""
    http_requests_total.labels(method=method, path=path, status=str(status)).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration)


def record_db_query(operation: str, duration: float) -> None:
    """Record database query metrics."""
    db_query_duration_seconds.labels(operation=operation).observe(duration)


def record_llm_request(model: str, status: str, duration: float) -> None:
    """Record LLM request metrics."""
    llm_requests_total.labels(model=model, status=status).inc()
    llm_request_duration_seconds.labels(model=model).observe(duration)


def record_llm_tokens(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Record LLM token usage."""
    if prompt_tokens:
        llm_tokens_total.labels(model=model, type="prompt").inc(prompt_tokens)
    if completion_tokens:
        llm_tokens_total.labels(model=model, type="completion").inc(completion_tokens)


def record_pdf_parse(duration: float, pages: int) -> None:
    """Record PDF parsing metrics."""
    pdf_parse_duration_seconds.observe(duration)
    pdf_parse_pages.observe(pages)
