"""Application configuration.

All application settings are declared here using ``pydantic-settings``.
Values are loaded from environment variables (case-insensitive) and,
optionally, from a ``.env`` file in the project root.

Database-agnosticism
--------------------
The ``database_url`` field accepts any SQLAlchemy async URL.  The
``app.infrastructure.database`` module auto-detects the dialect and
applies driver-specific settings (pool class, connect_args, etc.):

    SQLite (development):   sqlite+aiosqlite:///./data/doctrace.db
    PostgreSQL (production): postgresql+asyncpg://user:pass@host/db

Switching databases requires **only** changing ``DATABASE_URL`` in the
environment — no code changes.

LLM provider-agnosticism
-------------------------
The ``openrouter_base_url`` and ``llm_model`` fields make the LLM
provider swappable via environment variables.  See ``.env.example`` for
a provider comparison table.

Usage
-----
Inject into FastAPI handlers::

    from app.core.config import Settings, get_settings
    from fastapi import Depends

    @router.get("/example")
    async def example(settings: Settings = Depends(get_settings)):
        return {"model": settings.llm_model}

Or access the singleton directly::

    from app.core.config import get_settings
    settings = get_settings()

Testing
-------
Reset the cache between tests to isolate env-var patches::

    from app.core.config import get_settings
    get_settings.cache_clear()
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables.

    All fields map 1-to-1 with environment variable names (case-insensitive).
    Fields without defaults are required; the application raises a
    ``ValidationError`` at startup if required fields are absent.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────

    app_name: str = Field(default="DocTrace AI")
    app_version: str = Field(default="0.1.0")
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description=(
            "Deployment environment.  Controls log format (JSON in production), "
            "Swagger UI visibility, and debug features."
        ),
    )
    debug: bool = Field(default=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )

    # ── Database (SQLAlchemy async URL) ───────────────────────────────────────
    #
    # Default: SQLite file-based database for zero-dependency development.
    # Switch to PostgreSQL for production by changing this URL — no code changes.
    #
    # SQLite:     sqlite+aiosqlite:///./data/doctrace.db
    # PostgreSQL: postgresql+asyncpg://user:pass@host:5432/dbname

    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/doctrace.db",
        description=(
            "SQLAlchemy async database URL.  The dialect prefix selects the driver:\n"
            "  sqlite+aiosqlite:///  — SQLite (development, no external service)\n"
            "  postgresql+asyncpg:// — PostgreSQL (production)\n"
            "Synchronous drivers (sqlite://, postgresql://) are rejected at startup."
        ),
    )
    database_echo_sql: bool = Field(
        default=False,
        description="Log every SQL statement.  Enable only for debugging; very noisy.",
    )

    # ── MongoDB ───────────────────────────────────────────────────────────────

    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        description=(
            "Motor (async MongoDB) connection string.  "
            "MongoDB is optional: the application starts without it, "
            "but LLM generation endpoints return 503 until it is reachable."
        ),
    )
    mongodb_database_name: str = Field(
        default="doctrace_ai",
        description="MongoDB database name for LLM generation results.",
    )

    # ── LLM (OpenAI-compatible — OpenRouter by default) ───────────────────────

    openrouter_api_key: str = Field(
        default="",
        description=(
            "API key for the LLM provider.  "
            "OpenRouter: https://openrouter.ai/keys.  "
            "OpenAI: sk-… key.  Required for LLM generation."
        ),
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description=(
            "Base URL for the OpenAI-compatible LLM API.  "
            "Change to switch providers (see .env.example for a comparison table)."
        ),
    )
    llm_model: str = Field(
        default="google/gemini-2.5-flash",
        description=(
            "LLM model identifier.  OpenRouter format: 'provider/model'.  "
            "Changing this env var is the only action required to switch models."
        ),
    )
    llm_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    llm_retry_min_wait_seconds: float = Field(default=1.0, ge=0.0)
    llm_retry_max_wait_seconds: float = Field(default=30.0, ge=1.0)

    # ── File upload ───────────────────────────────────────────────────────────

    max_upload_size_mb: int = Field(default=50, ge=1, le=500)

    # ── Pagination ────────────────────────────────────────────────────────────

    default_page_size: int = Field(default=20, ge=1, le=100)
    max_page_size: int = Field(default=100, ge=1, le=1000)

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def max_upload_size_bytes(self) -> int:
        """Return the maximum upload size in bytes (derived from MB setting)."""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_development(self) -> bool:
        """Return True when running in a development environment."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Return True when running in a production environment."""
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        """Return True when the configured database is SQLite."""
        return "sqlite" in self.database_url.lower()

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("database_url", mode="before")
    @classmethod
    def require_async_driver(cls, v: str) -> str:
        """Reject synchronous database drivers at startup.

        Synchronous drivers block the event loop and are incompatible with
        FastAPI's async architecture.  The validator fails fast with a clear
        message rather than producing obscure runtime errors under load.

        Raises:
            ValueError: If the URL uses a synchronous driver prefix.
        """
        sync_prefixes = {
            "sqlite://": "sqlite+aiosqlite://",
            "postgresql://": "postgresql+asyncpg://",
            "mysql://": "mysql+aiomysql://",
        }
        for sync_prefix, async_prefix in sync_prefixes.items():
            if isinstance(v, str) and v.startswith(sync_prefix):
                raise ValueError(
                    f"database_url uses a synchronous driver ('{sync_prefix}').  "
                    f"Replace it with the async equivalent: '{async_prefix}...'"
                )
        return v

    @model_validator(mode="after")
    def warn_missing_llm_key(self) -> Settings:
        """Emit a startup warning if the LLM API key is absent.

        The application starts successfully without a key; LLM generation
        endpoints will return 503 at request time.  This warning surfaces
        misconfiguration before the first LLM call.
        """
        if not self.openrouter_api_key:
            logging.warning(
                "OPENROUTER_API_KEY is not set.  "
                "LLM generation endpoints will return 503 until a key is configured."
            )
        return self

    @model_validator(mode="after")
    def validate_page_size_ordering(self) -> Settings:
        """Ensure default_page_size does not exceed max_page_size."""
        if self.default_page_size > self.max_page_size:
            raise ValueError(
                f"default_page_size ({self.default_page_size}) "
                f"must be ≤ max_page_size ({self.max_page_size})"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    The ``.env`` file is parsed on first call; subsequent calls return the
    cached ``Settings`` instance.

    To reset during testing::

        from app.core.config import get_settings
        get_settings.cache_clear()

    Returns:
        The singleton ``Settings`` instance for this process.
    """
    return Settings()
