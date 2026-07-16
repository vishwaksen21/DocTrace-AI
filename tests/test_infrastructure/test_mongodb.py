"""Tests for app/infrastructure/mongodb.py (Module 2).

Test strategy:
    - All tests use ``unittest.mock.AsyncMock`` and ``MagicMock`` to mock
      the Motor client.  No real MongoDB connection is required.
    - This keeps the tests as fast unit tests, not integration tests.
    - The mock validates that the module calls the Motor API correctly.

What is tested:
    - init_mongo sets module-level globals
    - close_mongo clears them and calls client.close()
    - get_database returns the database or raises RuntimeError
    - check_mongo_health returns True on ping success
    - check_mongo_health returns False on ConnectionFailure
    - check_mongo_health returns False when client is not initialised
    - ensure_indexes calls create_index on the correct collection
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import ServerSelectionTimeoutError

import app.infrastructure.mongodb as mongo_module
from app.infrastructure.mongodb import (
    check_mongo_health,
    close_mongo,
    ensure_indexes,
    get_database,
    init_mongo,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Provide a minimal Settings mock for MongoDB tests."""
    settings = MagicMock()
    settings.mongodb_url = "mongodb://localhost:27017"
    settings.mongodb_database_name = "test_doctrace"
    return settings


@pytest.fixture(autouse=True)
async def reset_mongo_state():
    """Ensure each test starts with uninitialised MongoDB module state."""
    # Clear any leftover state
    mongo_module._client = None
    mongo_module._database = None
    yield
    # Teardown: close without caring about errors
    mongo_module._client = None
    mongo_module._database = None


# ── Lifecycle ─────────────────────────────────────────────────────────────────


class TestMongoLifecycle:
    """Verify init_mongo / close_mongo manage module state correctly."""

    async def test_init_mongo_sets_globals(self, mock_settings) -> None:
        with patch("app.infrastructure.mongodb.AsyncIOMotorClient") as mock_client_cls:
            mock_client_instance = MagicMock()
            mock_client_cls.return_value = mock_client_instance
            mock_db = MagicMock()
            mock_client_instance.__getitem__ = MagicMock(return_value=mock_db)

            await init_mongo(mock_settings)

            assert mongo_module._client is not None
            assert mongo_module._database is not None
            mock_client_cls.assert_called_once_with(
                mock_settings.mongodb_url,
                serverSelectionTimeoutMS=5_000,
            )

    async def test_close_mongo_clears_globals(self, mock_settings) -> None:
        mock_client = MagicMock()
        mongo_module._client = mock_client
        mongo_module._database = MagicMock()

        await close_mongo()

        assert mongo_module._client is None
        assert mongo_module._database is None
        mock_client.close.assert_called_once()

    async def test_close_mongo_is_safe_when_not_initialised(self) -> None:
        """close_mongo must not raise if init_mongo was never called."""
        await close_mongo()  # should not raise


# ── get_database ──────────────────────────────────────────────────────────────


class TestGetDatabase:
    """Verify get_database raises or returns correctly."""

    def test_raises_when_not_initialised(self) -> None:
        with pytest.raises(RuntimeError, match="not initialised"):
            get_database()

    def test_returns_database_when_initialised(self) -> None:
        mock_db = MagicMock()
        mongo_module._database = mock_db
        result = get_database()
        assert result is mock_db


# ── Health check ──────────────────────────────────────────────────────────────


class TestCheckMongoHealth:
    """Verify health check behaviour under various conditions."""

    async def test_returns_false_when_not_initialised(self) -> None:
        result = await check_mongo_health()
        assert result is False

    async def test_returns_true_on_successful_ping(self) -> None:
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})
        mongo_module._client = mock_client

        result = await check_mongo_health()

        assert result is True
        mock_client.admin.command.assert_awaited_once_with("ping")

    async def test_returns_false_on_connection_failure(self) -> None:
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(side_effect=ServerSelectionTimeoutError("timeout"))
        mongo_module._client = mock_client

        result = await check_mongo_health()
        assert result is False

    async def test_returns_false_on_unexpected_error(self) -> None:
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(side_effect=RuntimeError("boom"))
        mongo_module._client = mock_client

        result = await check_mongo_health()
        assert result is False


# ── ensure_indexes ────────────────────────────────────────────────────────────


class TestEnsureIndexes:
    """Verify ensure_indexes creates the required indexes."""

    async def test_skips_gracefully_when_not_initialised(self) -> None:
        """ensure_indexes must not raise when MongoDB is unavailable."""
        await ensure_indexes()  # should not raise

    async def test_calls_create_index_on_collection(self) -> None:
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.create_index = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mongo_module._database = mock_db

        await ensure_indexes()

        # Should have called create_index at least twice (two indexes)
        assert mock_collection.create_index.await_count >= 2
