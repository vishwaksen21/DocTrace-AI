"""Compatibility shim — import from ``app.core.config`` instead.

This module re-exports ``Settings`` and ``get_settings`` so that any
code written before the M1 refactor continues to work.  New code must
import directly from ``app.core.config``.

.. deprecated::
    Use ``from app.core.config import Settings, get_settings`` instead.
"""

from app.core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
