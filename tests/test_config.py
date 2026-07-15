"""Unit tests for app/core/config.py.

Tests cover:
- Default values are correct
- Environment variable overrides work
- Validators reject synchronous database drivers
- Page size ordering constraint is enforced
- Computed properties derive correctly
- LRU cache can be cleared between tests
"""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings


class TestSettingsDefaults:
    """Verify all default values are correct out of the box."""

    def test_default_environment_is_development(self) -> None:
        s = Settings()
        assert s.environment == "development"

    def test_default_database_is_sqlite(self) -> None:
        s = Settings()
        assert "sqlite" in s.database_url
        assert "aiosqlite" in s.database_url

    def test_default_llm_model(self) -> None:
        s = Settings()
        assert s.llm_model == "google/gemini-2.5-flash"

    def test_default_llm_base_url_is_openrouter(self) -> None:
        s = Settings()
        assert "openrouter.ai" in s.openrouter_base_url

    def test_default_page_sizes_are_consistent(self) -> None:
        s = Settings()
        assert s.default_page_size <= s.max_page_size

    def test_max_upload_size_bytes_derived_from_mb(self) -> None:
        s = Settings(max_upload_size_mb=10)
        assert s.max_upload_size_bytes == 10 * 1024 * 1024

    def test_is_development_property(self) -> None:
        s = Settings(environment="development")
        assert s.is_development is True
        assert s.is_production is False

    def test_is_production_property(self) -> None:
        s = Settings(environment="production")
        assert s.is_production is True
        assert s.is_development is False

    def test_is_sqlite_property_with_sqlite_url(self) -> None:
        s = Settings(database_url="sqlite+aiosqlite:///:memory:")
        assert s.is_sqlite is True

    def test_is_sqlite_property_with_postgres_url(self) -> None:
        s = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
        assert s.is_sqlite is False


class TestSettingsValidators:
    """Verify field validators reject invalid input."""

    def test_synchronous_sqlite_url_is_rejected(self) -> None:
        with pytest.raises(Exception, match="aiosqlite"):
            Settings(database_url="sqlite:///./doctrace.db")

    def test_synchronous_postgres_url_is_rejected(self) -> None:
        with pytest.raises(Exception, match="asyncpg"):
            Settings(database_url="postgresql://user:pass@localhost/db")

    def test_async_sqlite_url_is_accepted(self) -> None:
        s = Settings(database_url="sqlite+aiosqlite:///:memory:")
        assert "aiosqlite" in s.database_url

    def test_async_postgres_url_is_accepted(self) -> None:
        s = Settings(database_url="postgresql+asyncpg://user:pass@localhost/db")
        assert "asyncpg" in s.database_url

    def test_default_page_size_exceeding_max_is_rejected(self) -> None:
        with pytest.raises(Exception, match="default_page_size"):
            Settings(default_page_size=200, max_page_size=100)

    def test_equal_default_and_max_page_size_is_accepted(self) -> None:
        s = Settings(default_page_size=50, max_page_size=50)
        assert s.default_page_size == s.max_page_size


class TestSettingsEnvOverride:
    """Verify environment variables correctly override defaults."""

    def test_llm_model_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
        s = Settings()
        assert s.llm_model == "openai/gpt-4o-mini"

    def test_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        s = Settings()
        assert s.environment == "production"
        assert s.is_production is True

    def test_api_key_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
        s = Settings()
        assert s.openrouter_api_key == "sk-or-test-key"

    def test_database_url_override_to_sqlite_memory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        s = Settings()
        assert ":memory:" in s.database_url


class TestGetSettingsCache:
    """Verify the LRU cache behaviour of get_settings()."""

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_env_var_change_reflected_after_cache_clear(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _ = get_settings()  # prime the cache
        monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o")
        get_settings.cache_clear()
        s = get_settings()
        assert s.llm_model == "openai/gpt-4o"
