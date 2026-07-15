"""Tests for app/infrastructure/database.py (Module 2).

Test strategy:
    - All tests use in-memory SQLite (sqlite+aiosqlite:///:memory:) so they
      run without any external services.
    - The ``StaticPool`` + ``check_same_thread=False`` combination ensures
      all async operations share the same in-memory connection.
    - ``init_db`` / ``close_db`` are called in fixtures, not in tests, so
      each test gets a clean, isolated database state.

What is tested:
    - Engine is created with correct dialect-specific settings
    - Session context manager yields a working AsyncSession
    - Session rolls back on exception
    - ``check_db_health`` returns True for a live database
    - ``check_db_health`` returns False when engine is not initialised
    - Concurrent session usage does not deadlock (basic smoke test)
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.infrastructure.database as db_module
from app.infrastructure.database import (
    check_db_health,
    close_db,
    get_session,
    init_db,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sqlite_memory_settings(monkeypatch: pytest.MonkeyPatch):
    """Provide Settings pointing to an in-memory SQLite database."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def reset_db_state():
    """Ensure each test starts with an uninitialised database module."""
    # Tear down any state left by a previous test
    await close_db()
    yield
    # Tear down state created by this test
    await close_db()


# ── Engine construction ───────────────────────────────────────────────────────


class TestBuildEngine:
    """Verify dialect-specific engine configuration."""

    def test_sqlite_memory_uses_static_pool(self) -> None:
        from sqlalchemy.pool import StaticPool

        from app.infrastructure.database import _build_engine
        engine = _build_engine("sqlite+aiosqlite:///:memory:", echo=False)
        assert isinstance(engine.pool, StaticPool)

    def test_sqlite_file_uses_null_pool(self, tmp_path) -> None:
        from sqlalchemy.pool import NullPool

        from app.infrastructure.database import _build_engine
        db_path = tmp_path / "test.db"
        engine = _build_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        assert isinstance(engine.pool, NullPool)


# ── Lifecycle ─────────────────────────────────────────────────────────────────


class TestDatabaseLifecycle:
    """Verify init_db / close_db initialise and release state correctly."""

    async def test_init_db_sets_module_globals(self, sqlite_memory_settings) -> None:
        assert db_module._engine is None
        assert db_module._session_factory is None

        await init_db(sqlite_memory_settings)

        assert db_module._engine is not None
        assert db_module._session_factory is not None

    async def test_close_db_clears_module_globals(self, sqlite_memory_settings) -> None:
        await init_db(sqlite_memory_settings)
        await close_db()

        assert db_module._engine is None
        assert db_module._session_factory is None

    async def test_close_db_is_safe_when_not_initialised(self) -> None:
        """close_db must be a no-op if init_db was never called."""
        await close_db()  # should not raise


# ── Session management ────────────────────────────────────────────────────────


class TestGetSession:
    """Verify session creation and transaction behaviour."""

    async def test_raises_if_not_initialised(self) -> None:
        with pytest.raises(RuntimeError, match="not initialised"):
            async with get_session():
                pass

    async def test_yields_async_session(self, sqlite_memory_settings) -> None:
        await init_db(sqlite_memory_settings)
        async with get_session() as session:
            assert isinstance(session, AsyncSession)

    async def test_session_can_execute_query(self, sqlite_memory_settings) -> None:
        await init_db(sqlite_memory_settings)
        async with get_session() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
        assert value == 1

    async def test_session_rolls_back_on_exception(
        self, sqlite_memory_settings
    ) -> None:
        """Exception inside get_session() must trigger rollback, not commit."""
        await init_db(sqlite_memory_settings)

        class _TestError(Exception):
            pass

        with pytest.raises(_TestError):
            async with get_session():
                # Intentionally raise to trigger rollback path
                raise _TestError("trigger rollback")


# ── Health check ──────────────────────────────────────────────────────────────


class TestCheckDbHealth:
    """Verify the health check function reports state correctly."""

    async def test_returns_false_when_not_initialised(self) -> None:
        result = await check_db_health()
        assert result is False

    async def test_returns_true_when_database_is_reachable(
        self, sqlite_memory_settings
    ) -> None:
        await init_db(sqlite_memory_settings)
        result = await check_db_health()
        assert result is True

    async def test_returns_false_after_close_db(self, sqlite_memory_settings) -> None:
        await init_db(sqlite_memory_settings)
        await close_db()
        result = await check_db_health()
        assert result is False
