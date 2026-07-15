"""Application configuration.

All application settings are declared here using pydantic-settings.
Values are loaded from environment variables (case-insensitive) and,
optionally, from a `.env` file in the project root.

Usage
-----
Inject into FastAPI route handlers::

    from app.config import Settings, get_settings
    from fastapi import Depends

    @router.get("/example")
    async def example(settings: Settings = Depends(get_settings)):
        return {"model": settings.llm_model}

Or access directly::

    from app.config import get_settings
    settings = get_settings()

Design notes
------------
- ``get_settings`` is decorated with ``@lru_cache`` so the .env file is
  parsed exactly once per process.  Unit tests that need different config
  should call ``get_settings.cache_clear()`` before patching env vars.
- Never import ``Settings`` directly to construct instances in application
  code; always go through ``get_settings()`` so the cache is respected.
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
    Fields without defaults are required; the application will raise a
    ``ValidationError`` at startup if they are missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # silently discard unknown env vars
    )

    # ── Application ──────────────────────────────────────────────────────────

    app_name: str = Field(default="DocTrace AI", description="Human-readable app name")
    app_version: str = Field(default="0.1.0", description="Semantic version string")
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment. Controls log format and debug features.",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode. Never enable in production.",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Minimum log level to emit.",
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────────

    database_url: str = Field(
        default="postgresql+asyncpg://doctrace:doctrace@localhost:5432/doctrace_db",
        description=(
            "SQLAlchemy async database URL.  Must use the asyncpg driver "
            "(postgresql+asyncpg://...).  Never use a synchronous driver."
        ),
    )
    database_pool_size: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of permanent connections in the SQLAlchemy pool.",
    )
    database_max_overflow: int = Field(
        default=20,
        ge=0,
        le=100,
        description="Extra connections allowed beyond pool_size under peak load.",
    )
    database_echo_sql: bool = Field(
        default=False,
        description="Log every SQL statement.  Enable only for debugging; very noisy.",
    )

    # ── MongoDB ───────────────────────────────────────────────────────────────

    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        description="Motor (async MongoDB) connection string.",
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
            "For OpenRouter: obtain at https://openrouter.ai/keys.  "
            "For OpenAI: use an sk-... key.  "
            "Required for any LLM generation request."
        ),
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description=(
            "Base URL for the OpenAI-compatible LLM API.  "
            "Change to switch providers without code changes:  "
            "  OpenAI:  https://api.openai.com/v1  "
            "  Groq:    https://api.groq.com/openai/v1  "
            "  Gemini:  https://generativelanguage.googleapis.com/v1beta/openai/"
        ),
    )
    llm_model: str = Field(
        default="google/gemini-2.5-flash",
        description=(
            "LLM model identifier passed to the provider.  "
            "OpenRouter format: 'provider/model' (e.g. 'openai/gpt-4o-mini').  "
            "OpenAI format: 'gpt-4o-mini'.  "
            "Change here or via env var to switch models with zero code changes."
        ),
    )
    llm_timeout_seconds: float = Field(
        default=60.0,
        ge=5.0,
        le=300.0,
        description="Total timeout (seconds) for a single LLM API call.",
    )
    llm_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts on transient LLM errors.",
    )
    llm_retry_min_wait_seconds: float = Field(
        default=1.0,
        description="Minimum wait (seconds) between LLM retry attempts (exponential backoff).",
    )
    llm_retry_max_wait_seconds: float = Field(
        default=30.0,
        description="Maximum wait (seconds) between LLM retry attempts.",
    )

    # ── File upload ───────────────────────────────────────────────────────────

    max_upload_size_mb: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum allowed PDF upload size in megabytes.",
    )

    # ── Pagination ────────────────────────────────────────────────────────────

    default_page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Default number of items returned per page.",
    )
    max_page_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of items a client may request per page.",
    )

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

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure the database URL uses the async asyncpg driver.

        Raises:
            ValueError: If the URL uses a synchronous psycopg2 driver.
        """
        if isinstance(v, str) and v.startswith("postgresql://"):
            raise ValueError(
                "database_url must use the async driver: "
                "replace 'postgresql://' with 'postgresql+asyncpg://'"
            )
        return v

    @model_validator(mode="after")
    def warn_missing_api_key(self) -> Settings:
        """Emit a startup warning if the LLM API key is missing.

        The application can start without a key; it will only fail at
        LLM generation time.  This warning helps catch misconfiguration early.
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
                f"default_page_size ({self.default_page_size}) must be "
                f"<= max_page_size ({self.max_page_size})"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance.

    The .env file is parsed on first call; subsequent calls return the
    cached instance from ``lru_cache``.

    To reset during testing::

        from app.config import get_settings
        get_settings.cache_clear()

    Returns:
        The singleton ``Settings`` instance for this process.
    """
    return Settings()
