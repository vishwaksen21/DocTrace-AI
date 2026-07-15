"""Motor (async MongoDB) client infrastructure.

Manages the lifecycle of the Motor client and provides a handle to the
configured database.

Why MongoDB for LLM output?
----------------------------
LLM responses are inherently schema-flexible — the structure of generated
test cases may evolve as prompts improve.  Storing them in MongoDB allows:
    - Schema-free persistence of the raw + parsed response together
    - Re-processing raw responses if the parsing schema changes
    - No Alembic migrations when the LLM output format evolves

The relational schema (PostgreSQL/SQLite) stores stable structured data
(documents, versions, nodes).  MongoDB stores the fluid LLM artifacts.

Graceful degradation
--------------------
MongoDB is optional at startup.  The application starts successfully even
if MongoDB is unreachable.  LLM generation endpoints return HTTP 503 until
connectivity is established.  This prevents a MongoDB outage from taking
down the entire service.

All MongoDB-dependent operations must call ``get_database()`` rather than
accessing the module-level ``_database`` directly.  ``get_database()``
raises a clear ``RuntimeError`` if the client was never initialised, rather
than producing obscure ``AttributeError`` or ``NoneType`` errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.core.constants import MONGO_COLLECTION_GENERATIONS
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import Settings

logger = get_logger(__name__)

# ── Module-level singletons ───────────────────────────────────────────────────

_client: AsyncIOMotorClient | None = None  # type: ignore[type-arg]
_database: AsyncIOMotorDatabase | None = None  # type: ignore[type-arg]


# ── Lifecycle ─────────────────────────────────────────────────────────────────


async def init_mongo(settings: Settings) -> None:
    """Initialise the Motor MongoDB client and select the target database.

    The client is created with a short ``serverSelectionTimeoutMS`` (5 s)
    so startup fails fast if MongoDB is misconfigured, rather than hanging
    indefinitely.  Individual operation timeouts are governed by Motor's
    default socket timeout.

    Args:
        settings: Application settings supplying ``mongodb_url`` and
            ``mongodb_database_name``.
    """
    global _client, _database

    _client = AsyncIOMotorClient(
        settings.mongodb_url,
        serverSelectionTimeoutMS=5_000,
    )
    _database = _client[settings.mongodb_database_name]

    logger.info(
        "MongoDB client initialised",
        database=settings.mongodb_database_name,
    )


async def close_mongo() -> None:
    """Close the MongoDB client and release all connections.

    Must be called during application shutdown.  Safe to call even if
    ``init_mongo`` was not called (no-op).
    """
    global _client, _database

    if _client is not None:
        _client.close()
        _client = None
        _database = None
        logger.info("MongoDB connection closed")


# ── Database accessor ─────────────────────────────────────────────────────────


def get_database() -> AsyncIOMotorDatabase:  # type: ignore[type-arg]
    """Return the active MongoDB database handle.

    This is the only authorised way to access the database from application
    code.  Calling this before ``init_mongo`` has been called raises a clear
    ``RuntimeError`` rather than propagating an obscure ``NoneType`` error.

    Returns:
        The ``AsyncIOMotorDatabase`` configured at startup.

    Raises:
        RuntimeError: If ``init_mongo()`` has not been called.
    """
    if _database is None:
        raise RuntimeError(
            "MongoDB database is not initialised.  "
            "Ensure init_mongo() is awaited during application startup."
        )
    return _database


# ── Health check ──────────────────────────────────────────────────────────────


async def check_mongo_health() -> bool:
    """Verify MongoDB connectivity by issuing an admin ``ping`` command.

    Used by the ``/health/ready`` endpoint to report readiness.

    Returns:
        ``True`` if MongoDB responds to ping within the server selection timeout.
        ``False`` on any connectivity or authentication error.
    """
    if _client is None:
        logger.warning("MongoDB health check skipped: client not initialised")
        return False

    try:
        await _client.admin.command("ping")
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.warning("MongoDB health check failed", error=str(e))
        return False
    except Exception as e:
        logger.error("MongoDB health check: unexpected error", exc_info=e)
        return False


# ── Index management ──────────────────────────────────────────────────────────


async def ensure_indexes() -> None:
    """Create MongoDB indexes required for efficient query patterns.

    Called once during application startup.  Motor ``create_index`` is
    idempotent — it no-ops when the index already exists.

    Index strategy:
        generation_results.selection_id   — lookup all results for a selection
        generation_results.(document_id, created_at DESC) — timeline queries
    """
    if _database is None:
        logger.warning("Skipping index creation: MongoDB not initialised")
        return

    collection = _database[MONGO_COLLECTION_GENERATIONS]

    await collection.create_index([("selection_id", 1)], background=True)
    await collection.create_index(
        [("document_id", 1), ("created_at", -1)],
        background=True,
    )

    logger.debug(
        "MongoDB indexes ensured",
        collection=MONGO_COLLECTION_GENERATIONS,
    )
