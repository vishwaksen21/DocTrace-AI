"""SQLAlchemy async database infrastructure.

Manages the lifecycle of the database engine and session factory.
The engine is created once at startup (``init_db``) and disposed at
shutdown (``close_db``).  All database access goes through ``get_session``.

Database-agnosticism
--------------------
The engine configuration adapts automatically to the dialect in the URL:

    SQLite (development)
    ├── check_same_thread=False  — aiosqlite runs in a worker thread
    ├── NullPool  (file-based)   — avoids "database is locked" on reconnect
    └── StaticPool (:memory:)   — keeps one connection for in-memory testing

    PostgreSQL (production)
    └── Default connection pool with configurable pool_size / max_overflow

Switching between SQLite and PostgreSQL requires changing only the
``DATABASE_URL`` environment variable.

Session lifecycle
-----------------
``get_session()`` is an ``asynccontextmanager`` that:
    1. Creates a new ``AsyncSession``
    2. Yields it to the caller
    3. Rolls back on any unhandled exception
    4. Closes the session on exit

The caller (service layer or FastAPI dependency) is responsible for
calling ``session.commit()`` after successful operations.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import Settings

logger = get_logger(__name__)

# ── Module-level singletons ───────────────────────────────────────────────────
# Initialised by init_db(); cleared by close_db().
# Using module-level state (rather than a class) keeps the API simple and
# mirrors how FastAPI manages application-lifetime resources.

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# ── Engine construction ───────────────────────────────────────────────────────


def _build_engine(database_url: str, echo: bool) -> AsyncEngine:
    """Construct an async SQLAlchemy engine for the given URL.

    Applies dialect-specific configuration automatically so the rest of
    the application remains database-agnostic.

    Args:
        database_url: Full SQLAlchemy async URL (e.g. ``sqlite+aiosqlite:///...``).
        echo: Whether to log all SQL statements (development only).

    Returns:
        A configured ``AsyncEngine`` instance.
    """
    is_sqlite = "sqlite" in database_url.lower()

    if is_sqlite:
        is_memory = ":memory:" in database_url
        return create_async_engine(
            database_url,
            echo=echo,
            connect_args={"check_same_thread": False},
            # StaticPool: single shared connection — required for in-memory SQLite
            #             so all operations see the same database state.
            # NullPool:   close connection immediately after use — prevents the
            #             "database is locked" error with file-based SQLite.
            poolclass=StaticPool if is_memory else NullPool,
        )

    # PostgreSQL or other dialects: use SQLAlchemy's default pool.
    # Pool size can be tuned via connection URL parameters when needed.
    return create_async_engine(database_url, echo=echo)


# ── Lifecycle ─────────────────────────────────────────────────────────────────


async def init_db(settings: Settings) -> None:
    """Initialise the database engine and session factory.

    Must be called exactly once during application startup, before any
    route handlers attempt database access.

    For SQLite file databases, the parent directory is created automatically
    so the application can start from a clean checkout without manual setup.

    Args:
        settings: Application settings supplying ``database_url`` and
            ``database_echo_sql``.
    """
    global _engine, _session_factory

    url = settings.database_url

    if settings.is_sqlite and ":memory:" not in url:
        _ensure_sqlite_dir(url)

    _engine = _build_engine(url, settings.database_echo_sql)
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Avoid lazy-load issues in async context
        autoflush=False,
        autocommit=False,
    )

    logger.info("Database initialised", url=_redact_url(url))


async def close_db() -> None:
    """Dispose the database engine and release all pooled connections.

    Must be called during application shutdown to avoid resource leaks.
    Safe to call even if ``init_db`` was not called (no-op).
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection closed")


# ── Session management ────────────────────────────────────────────────────────


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session scoped to a single unit of work.

    The session is automatically rolled back if an unhandled exception
    propagates out of the ``async with`` block.  The caller is responsible
    for committing after successful operations.

    Raises:
        RuntimeError: If ``init_db()`` has not been called.

    Example::

        async with get_session() as session:
            result = await session.execute(select(Document))
            await session.commit()
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database session factory is not initialised.  "
            "Ensure init_db() is awaited during application startup."
        )

    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ── Health check ──────────────────────────────────────────────────────────────


async def check_db_health() -> bool:
    """Verify database connectivity by executing a trivial query.

    Used by the ``/health/ready`` endpoint to report readiness.

    Returns:
        ``True`` if the database responds correctly.
        ``False`` on any connectivity or configuration error.
    """
    if _engine is None:
        logger.warning("Database health check skipped: engine not initialised")
        return False

    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except OperationalError as e:
        logger.warning("Database health check failed: operational error", error=str(e))
        return False
    except SQLAlchemyError as e:
        logger.error("Database health check failed: unexpected error", exc_info=e)
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create parent directories for the SQLite database file.

    Extracts the file path component from the URL and calls ``os.makedirs``
    with ``exist_ok=True``.  This makes fresh-checkout startup work without
    any manual directory creation.

    Args:
        database_url: A ``sqlite+aiosqlite:///path`` URL.
    """
    # sqlite+aiosqlite:///./data/doctrace.db → ./data/doctrace.db
    path = database_url.split("///", maxsplit=1)[-1]
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
        logger.debug("SQLite data directory ensured", path=directory)


def _redact_url(database_url: str) -> str:
    """Return a log-safe version of the database URL (no credentials).

    SQLite URLs contain no credentials, so they are returned unchanged.
    For URLs with ``user:password@host``, the credential portion is
    replaced with ``***``.

    Args:
        database_url: The full database URL.

    Returns:
        A redacted URL safe for logging and error messages.
    """
    if "sqlite" in database_url:
        return database_url

    try:
        scheme, rest = database_url.split("://", 1)
        if "@" in rest:
            _, host_part = rest.rsplit("@", 1)
            return f"{scheme}://***@{host_part}"
    except ValueError:
        pass

    return "<redacted>"
