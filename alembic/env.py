"""Alembic migration environment.

This file is called by Alembic during ``alembic upgrade``, ``downgrade``,
and ``revision --autogenerate``.  It configures the database connection and
registers the project's ``Base.metadata`` for autogenerate.

Async SQLAlchemy
----------------
FastAPI uses ``sqlalchemy.ext.asyncio``.  Alembic historically expected a
synchronous engine, but since Alembic 1.11+ it supports async engines via
``run_async_migrations`` using ``connectable.run_sync()``.

We detect whether we are in ``--sql`` (offline) or normal (online) mode and
take the appropriate code path.

Environment variable injection
-------------------------------
The database URL is read from the ``DATABASE_URL`` environment variable (via
``app.core.config.get_settings``) rather than the ``sqlalchemy.url`` entry
in ``alembic.ini``.  This ensures Alembic always uses the same database as
the running application.  The ``alembic.ini`` value is retained as
documentation but is overridden at runtime.

Registering new models
-----------------------
Import every new model module in the block below so that ``Base.metadata``
sees all table definitions.  Alembic autogenerate will then detect new tables,
modified columns, and dropped columns automatically.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Register all ORM models ───────────────────────────────────────────────────
# Import every model module so that Base.metadata is fully populated before
# Alembic inspects it.  Add new model modules here as they are created.

from app.models.base import Base  # noqa: F401 — must import Base before models
from app.models.document import DocumentModel  # noqa: F401
from app.models.node import NodeModel  # noqa: F401
from app.models.selection import SelectionModel, SelectionNodeModel  # noqa: F401
from app.models.version import VersionModel  # noqa: F401

# ── Configuration ─────────────────────────────────────────────────────────────

# Alembic Config object; provides access to values in alembic.ini
config = context.config

# Override sqlalchemy.url with the value from application settings so
# Alembic always targets the same database as the running application.
from app.core.config import get_settings  # noqa: E402

_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.database_url)

# Set up Python logging using the [loggers] section of alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object that autogenerate will inspect
target_metadata = Base.metadata


# ── Migration helpers ─────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live database connection.

    Invoked via: ``alembic upgrade head --sql > migration.sql``
    Useful for reviewing the migration SQL before applying it.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations using a synchronous connection handle.

    Called from ``run_migrations_online`` via ``Connection.run_sync``, which
    bridges the async engine into the synchronous Alembic migration context.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Render the schema as individual statements (easier to review in PR)
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations synchronously within it.

    Uses ``connectable.run_sync`` to hand off a synchronous ``Connection``
    to Alembic, which cannot be made async.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Never pool connections in migration runs
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Apply migrations against a live database.

    Invoked via: ``alembic upgrade head``
    """
    asyncio.run(run_async_migrations())


# ── Entry point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
