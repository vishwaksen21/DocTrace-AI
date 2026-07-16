"""Pytest fixtures for service layer tests.

Sets up an in-memory SQLite database using ``aiosqlite`` for SQL repository dependencies.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.base import Base


@pytest.fixture
async def service_db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a function-scoped in-memory SQLite database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def service_session(service_db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactionally isolated AsyncSession for each service test."""
    async_session = async_sessionmaker(
        service_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with async_session() as session:
        yield session
        await session.rollback()
