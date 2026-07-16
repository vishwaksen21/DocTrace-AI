"""Pytest fixtures for API integration tests.

Sets up a test client with dependency overrides for the SQL database and MongoDB.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_mongo
from app.main import app
from app.models.base import Base


@pytest.fixture(scope="module")
async def api_db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a module-scoped file-based SQLite database engine for testing."""
    import os

    db_file = "test_api.db"
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass

    # Create a new engine for testing
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Set the module-level engine so get_session works
    from app.infrastructure import database
    database._engine = engine
    database._session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    try:
        yield engine
    finally:
        await engine.dispose()
        database._engine = None
        database._session_factory = None
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass


@pytest.fixture
async def api_session(api_db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactionally isolated AsyncSession for dependency override."""
    from app.infrastructure.database import _session_factory
    assert _session_factory is not None

    async with _session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_mongo_db() -> MagicMock:
    """Provide a mock MongoDB database using MagicMock."""
    db = MagicMock()
    collection = MagicMock()

    # Configure default collection operations to prevent errors
    insert_res = MagicMock()
    insert_res.inserted_id = ObjectId()
    collection.insert_one = AsyncMock(return_value=insert_res)
    collection.update_one = AsyncMock()
    collection.find_one = AsyncMock(return_value=None)
    collection.find_one_and_update = AsyncMock(return_value=None)
    collection.count_documents = AsyncMock(return_value=0)

    # Create a cursor mock that chains properly
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])

    collection.find.return_value = cursor

    db.__getitem__.return_value = collection
    return db


@pytest.fixture
async def client(
    api_session: AsyncSession,
    mock_mongo_db: Any,
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient configured with test dependency overrides."""
    # Override get_db dependency to use the isolated test session
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield api_session

    # Override get_mongo dependency to use the mock mongo database
    def override_get_mongo() -> Any:
        return mock_mongo_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_mongo] = override_get_mongo

    # Also patch init_db/close_db to prevent lifespan from re-initializing
    from unittest.mock import AsyncMock, patch
    patch1 = patch("app.api.deps.get_database", return_value=mock_mongo_db)
    patch2 = patch("app.repositories.generation.get_database", return_value=mock_mongo_db)
    patch3 = patch("app.infrastructure.database.init_db", AsyncMock())
    patch4 = patch("app.infrastructure.database.close_db", AsyncMock())

    with patch1, patch2, patch3, patch4:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()
