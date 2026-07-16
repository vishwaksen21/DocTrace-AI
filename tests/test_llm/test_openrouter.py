"""Unit tests for OpenRouterClient using mocked OpenAI Async client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIError, APITimeoutError, RateLimitError

from app.core.config import Settings
from app.llm import (
    LLMError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    OpenRouterClient,
)


@pytest.fixture
def test_settings() -> Settings:
    """Provide Settings override for LLM testing."""
    settings = Settings()
    settings.openrouter_api_key = "test-key"
    settings.llm_timeout_seconds = 10.0
    settings.llm_max_retries = 1
    settings.llm_retry_min_wait_seconds = 0.01
    settings.llm_retry_max_wait_seconds = 0.05
    return settings


@pytest.fixture
def mock_openai_client() -> MagicMock:
    """Provide a mock AsyncOpenAI client."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock()
    return client


class TestOpenRouterClient:
    """Tests for the OpenRouterClient class."""

    @pytest.mark.anyio
    async def test_complete_success(
        self,
        test_settings: Settings,
        mock_openai_client: MagicMock,
    ) -> None:
        # Mock successful completion response
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Validated Output JSON"
        mock_response.choices = [mock_choice]
        mock_response.model = "google/gemini-2.5-flash"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 40
        mock_response.usage.completion_tokens = 25
        mock_response.model_dump.return_value = {"id": "1"}

        mock_openai_client.chat.completions.create.return_value = mock_response

        with patch("app.llm.openrouter.AsyncOpenAI", return_value=mock_openai_client):
            client = OpenRouterClient(test_settings)
            messages = [LLMMessage(role="user", content="Hello")]
            response = await client.complete(messages)

            assert response.content == "Validated Output JSON"
            assert response.prompt_tokens == 40
            assert response.completion_tokens == 25
            assert response.model == "google/gemini-2.5-flash"
            assert response.raw_response == {"id": "1"}

            mock_openai_client.chat.completions.create.assert_called_once()

    @pytest.mark.anyio
    async def test_complete_rate_limit_error(
        self,
        test_settings: Settings,
        mock_openai_client: MagicMock,
    ) -> None:
        # Mock rate limit error
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"retry-after": "5.0"}

        exc = RateLimitError("Rate limited", response=mock_response, body=None)
        mock_openai_client.chat.completions.create.side_effect = exc

        with patch("app.llm.openrouter.AsyncOpenAI", return_value=mock_openai_client):
            client = OpenRouterClient(test_settings)
            messages = [LLMMessage(role="user", content="Hello")]

            with pytest.raises(LLMRateLimitError) as info:
                await client.complete(messages)

            assert "Rate limit exceeded" in str(info.value)
            assert info.value.retry_after == 5.0

    @pytest.mark.anyio
    async def test_complete_timeout_error(
        self,
        test_settings: Settings,
        mock_openai_client: MagicMock,
    ) -> None:
        # Mock timeout error
        exc = APITimeoutError(request=MagicMock())
        mock_openai_client.chat.completions.create.side_effect = exc

        with patch("app.llm.openrouter.AsyncOpenAI", return_value=mock_openai_client):
            client = OpenRouterClient(test_settings)
            messages = [LLMMessage(role="user", content="Hello")]

            with pytest.raises(LLMTimeoutError) as info:
                await client.complete(messages)

            assert "timed out" in str(info.value)

    @pytest.mark.anyio
    async def test_complete_provider_error(
        self,
        test_settings: Settings,
        mock_openai_client: MagicMock,
    ) -> None:
        # Mock standard API error
        exc = APIError("Authentication failed", request=MagicMock(), body=None)
        exc.response = MagicMock()
        exc.response.status_code = 401
        mock_openai_client.chat.completions.create.side_effect = exc

        with patch("app.llm.openrouter.AsyncOpenAI", return_value=mock_openai_client):
            client = OpenRouterClient(test_settings)
            messages = [LLMMessage(role="user", content="Hello")]

            with pytest.raises(LLMProviderError) as info:
                await client.complete(messages)

            assert "Provider API error" in str(info.value)

    @pytest.mark.anyio
    async def test_complete_generic_error(
        self,
        test_settings: Settings,
        mock_openai_client: MagicMock,
    ) -> None:
        # Mock unexpected generic exception
        mock_openai_client.chat.completions.create.side_effect = RuntimeError("network crash")

        with patch("app.llm.openrouter.AsyncOpenAI", return_value=mock_openai_client):
            client = OpenRouterClient(test_settings)
            messages = [LLMMessage(role="user", content="Hello")]

            with pytest.raises(LLMError) as info:
                await client.complete(messages)

            assert "Unexpected LLM error" in str(info.value)

    @pytest.mark.anyio
    async def test_health_check(
        self,
        test_settings: Settings,
        mock_openai_client: MagicMock,
    ) -> None:
        # Ensure that context manager resolves to the client mock
        mock_openai_client.__aenter__.return_value = mock_openai_client

        # 1. Success check
        mock_openai_client.chat.completions.create.return_value = MagicMock()
        with patch("app.llm.openrouter.AsyncOpenAI", return_value=mock_openai_client):
            client = OpenRouterClient(test_settings)
            assert await client.health_check() is True

        # 2. Failure check
        mock_openai_client.chat.completions.create.side_effect = RuntimeError("no network")
        with patch("app.llm.openrouter.AsyncOpenAI", return_value=mock_openai_client):
            client = OpenRouterClient(test_settings)
            assert await client.health_check() is False
