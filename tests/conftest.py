"""Pytest fixtures shared across the entire test suite.

Module-specific fixtures (e.g., mock PDF bytes, mock LLM response)
live in their respective test sub-packages.  Only truly cross-cutting
fixtures belong here.

Fixture lifecycle:
    - ``settings_override``: function-scoped; resets the settings cache
      after every test so tests that patch env vars are isolated.
    - ``anyio_backend``: session-scoped; pins async tests to asyncio.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Generator[None, None, None]:
    """Clear the ``get_settings`` LRU cache before and after each test.

    This ensures that patching environment variables with ``monkeypatch``
    produces a fresh ``Settings`` instance for the test, and that the
    patched values do not leak into subsequent tests.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Pin all async tests to the asyncio backend.

    Required by ``pytest-asyncio`` when using ``asyncio_mode = 'auto'``
    alongside ``anyio``.
    """
    return "asyncio"


def pytest_configure(config: pytest.Config) -> None:
    """Register global warning filters.

    Suppress the SQLAlchemy SAWarning that fires when an IntegrityError
    leaves a transaction deassociated from its connection on SQLite.  This
    is a known SQLite DDL auto-commit behaviour and does not affect the
    test outcome.  Silencing it keeps the output clean without masking
    real warnings.
    """
    import warnings

    warnings.filterwarnings(
        "ignore",
        message="transaction already deassociated from connection",
        category=UserWarning,  # SAWarning is a UserWarning subclass
    )
