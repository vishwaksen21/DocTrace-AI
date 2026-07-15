"""Structured logging configuration.

Configures structlog to emit JSON-formatted logs in production and
human-readable colorized logs in development.  Provides per-request
correlation IDs via a ``ContextVar`` that FastAPI middleware sets at the
start of each request.

Usage
-----
Call ``configure_logging`` once at application startup::

    from app.infrastructure.logging import configure_logging
    configure_logging(log_level="INFO", is_development=True)

Then obtain a named logger in any module::

    from app.infrastructure.logging import get_logger
    logger = get_logger(__name__)

    logger.info("Document parsed", document_id=str(doc.id), node_count=42)

Correlation IDs
---------------
Set once per request (e.g., in a FastAPI middleware)::

    from app.infrastructure.logging import set_request_id
    request_id = set_request_id()          # generates a UUID4
    # or
    request_id = set_request_id("my-id")  # use an existing ID from a header

Every subsequent log call within the same async context will include
``request_id`` automatically.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

import structlog
from structlog.types import EventDict, Processor

# ── Per-request correlation ID ────────────────────────────────────────────────
#
# ContextVar ensures each async task has its own isolated value, so concurrent
# requests do not bleed their IDs into each other's log entries.

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the correlation ID bound to the current async context.

    Returns an empty string if no ID has been set (e.g., during startup).
    """
    return _request_id_var.get()


def set_request_id(request_id: str | None = None) -> str:
    """Bind a correlation ID to the current async context.

    Generates a new UUID4 if ``request_id`` is not provided.  Call this
    once at the start of each request, typically in middleware.

    Args:
        request_id: An explicit ID string, or ``None`` to auto-generate.

    Returns:
        The ID that was set (useful when auto-generating).
    """
    rid = request_id or str(uuid4())
    _request_id_var.set(rid)
    return rid


# ── Custom structlog processors ───────────────────────────────────────────────


def _inject_request_id(
    logger: Any,
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """Structlog processor: inject the current request ID into every log event.

    This processor is position-sensitive; it must run after
    ``structlog.contextvars.merge_contextvars`` so that context vars are
    already present in ``event_dict`` when we inject.
    """
    rid = get_request_id()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def _drop_color_in_json(
    logger: Any,
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """Remove ANSI color codes that leak into JSON logs from some libraries."""
    # Only relevant in production (JSON) mode; no-op in development.
    return event_dict


# ── Public API ────────────────────────────────────────────────────────────────


def configure_logging(log_level: str = "INFO", is_development: bool = True) -> None:
    """Configure structlog and the stdlib ``logging`` root logger.

    Must be called exactly once, at application startup, before any
    logging calls are made.  Calling it more than once is safe but
    redundant (structlog is idempotent; stdlib handlers would be added twice,
    so this function is guarded against that).

    Args:
        log_level: Minimum log level string (e.g. ``"INFO"``, ``"DEBUG"``).
        is_development: If ``True``, render human-readable colored output.
                        If ``False``, render machine-parseable JSON.
    """
    # Processors shared between structlog-native and foreign (stdlib) loggers
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    # Final renderer: human-readable in dev, JSON in prod
    final_renderer: Processor
    if is_development:
        final_renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )
    else:
        final_renderer = structlog.processors.JSONRenderer()

    # Configure structlog itself
    structlog.configure(
        processors=[
            *shared_processors,
            # Wrap for the stdlib ProcessorFormatter (used by the handler below)
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Build a stdlib formatter that applies the same processor chain to both
    # structlog-issued and foreign (e.g., uvicorn, sqlalchemy) log records.
    formatter = structlog.stdlib.ProcessorFormatter(
        # Applied to foreign log records before final rendering
        foreign_pre_chain=shared_processors,
        processors=[
            # Remove structlog's internal "_record" and "_from_structlog" keys
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            final_renderer,
        ],
    )

    # Attach the handler to the root logger (guard against double-registration)
    root_logger = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    root_logger.setLevel(log_level.upper())

    # Silence high-volume third-party loggers that would overwhelm the output
    _silence_noisy_loggers()


def _silence_noisy_loggers() -> None:
    """Suppress overly verbose loggers from third-party libraries.

    These loggers produce per-request output that adds noise without value
    during normal operation.  They can be re-enabled individually by setting
    their level in application code if needed for debugging.
    """
    noisy: list[tuple[str, int]] = [
        ("uvicorn.access", logging.WARNING),
        ("sqlalchemy.engine", logging.WARNING),
        ("sqlalchemy.pool", logging.WARNING),
        ("motor", logging.WARNING),
        ("pymongo", logging.WARNING),
    ]
    for name, level in noisy:
        logging.getLogger(name).setLevel(level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named, bound structlog logger.

    The returned logger is bound to the module ``name`` so that log entries
    include a ``logger`` field for filtering and debugging.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A structlog ``BoundLogger`` instance.

    Example::

        logger = get_logger(__name__)
        logger.info("Node hashed", node_id=str(node.id), hash=node.content_hash)
        logger.warning("LLM retry", attempt=2, error="timeout")
        logger.error("Parse failed", exc_info=True)
    """
    return structlog.get_logger(name)
