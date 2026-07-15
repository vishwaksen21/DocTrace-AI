"""Compatibility shim — import from ``app.core.logging`` instead.

This module re-exports the logging utilities so that any code written
before the M1 refactor continues to work.  New code must import
directly from ``app.core.logging``.

.. deprecated::
    Use ``from app.core.logging import configure_logging, get_logger, ...``
"""

from app.core.logging import (
    configure_logging,
    get_logger,
    get_request_id,
    set_request_id,
)

__all__ = [
    "configure_logging",
    "get_logger",
    "get_request_id",
    "set_request_id",
]
