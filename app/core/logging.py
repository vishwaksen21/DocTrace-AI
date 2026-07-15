"""Structured logging configuration.

Configures structlog to emit JSON-formatted logs in production and
human-readable colorized logs in development.  Provides per-request
correlation IDs via a ``ContextVar`` that middleware sets at the start
of each HTTP request.

Why structlog?
--------------
- Processors compose cleanly (each is a pure function: EventDict → EventDict)
- Context variables enable async-safe per-request correlation IDs
- The same configuration controls both structlog-native loggers and stdlib
  loggers (uvicorn, SQLAlchemy), producing a unified log stream

Usage
-----
Call ``configure_logging`` once at startup::

    from app.core.logging import configure_logging
    configure_logging(log_level="INFO", is_development=True)

Obtain a named logger in any module::

    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("Document parsed", document_id=str(doc.id), nodes=42)

Set a per-request correlation ID (typically in middleware)::

    from app.core.logging import set_request_id
    request_id = set_request_id()           # auto-generates UUID4
    request_id = set_request_id("my-id")   # use an existing ID
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
# ContextVar isolates values per async task, so concurrent requests
# do not bleed their correlation IDs into each other's log lines.

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the correlation ID bound to the current async context.

    Returns an empty string when no ID has been set (e.g., during startup).
    """
    return _request_id_var.get()


def set_request_id(request_id: str | None = None) -> str:
    """Bind a correlation ID to the current async context.

    Generates a new UUID4 when ``request_id`` is ``None``.  Call once per
    request in middleware so all log lines within that request carry the ID.

    Args:
        request_id: An explicit ID (e.g., from an ``X-Request-ID`` header),
                    or ``None`` to auto-generate.

    Returns:
        The correlation ID that was set.
    """
    rid = request_id or str(uuid4())
    _request_id_var.set(rid)
    return rid


# ── Structlog processors ──────────────────────────────────────────────────────


def _inject_request_id(
    logger: Any,
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """Inject the current request correlation ID into every log event.

    Placed after ``merge_contextvars`` in the processor chain so that any
    context-variable-bound data is already merged before we add the ID.
    """
    rid = get_request_id()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


# ── Public API ────────────────────────────────────────────────────────────────


def configure_logging(log_level: str = "INFO", is_development: bool = True) -> None:
    """Configure structlog and the stdlib root logger.

    Must be called exactly once, before any logging occurs.  Calling it a
    second time is safe (the handler guard prevents double-registration).

    Args:
        log_level: Minimum log level string (e.g. ``"INFO"``, ``"DEBUG"``).
        is_development: ``True`` → colorized console renderer;
                        ``False`` → JSON renderer for log aggregation tools.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    final_renderer: Processor = (
        structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )
        if is_development
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            final_renderer,
        ],
    )

    root_logger = logging.getLogger()
    # Guard: only add handler if one hasn't been registered yet
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    root_logger.setLevel(log_level.upper())
    _silence_noisy_loggers()


def _silence_noisy_loggers() -> None:
    """Suppress high-volume third-party loggers that add noise in normal operation."""
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
