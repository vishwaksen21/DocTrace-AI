"""OpenRouter LLM Client implementation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.auth.circuit_breaker import OPENROUTER_BREAKER
from app.llm.base import (
    LLMError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
)

if TYPE_CHECKING:
    from app.core.config import Settings


class OpenRouterClient:
    """OpenRouter LLM client implementing LLMClientProtocol using OpenAI's Async SDK."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the OpenRouterClient.

        Args:
            settings: Application configuration settings.
        """
        self.settings = settings
        self._client = AsyncOpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key or "placeholder",
            timeout=settings.llm_timeout_seconds,
        )

    @property
    def model(self) -> str:
        """The model identifier configured for this client."""
        return self.settings.llm_model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Send completion request to OpenRouter with automatic exponential retries.

        Args:
            messages: Conversation history.
            temperature: Creative styling parameter.
            max_tokens: Limit on response tokens.
            response_format: Constraint on response format (e.g. JSON mode).
        """
        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Configure dynamic tenacity retry options based on runtime settings
        retryer = AsyncRetrying(
            stop=stop_after_attempt(self.settings.llm_max_retries + 1),
            wait=wait_exponential(
                multiplier=self.settings.llm_retry_min_wait_seconds,
                max=self.settings.llm_retry_max_wait_seconds,
            ),
            retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
            reraise=True,
        )

        async def _call_with_breaker() -> LLMResponse:
            return await retryer(
                OPENROUTER_BREAKER.call,
                self._call_api,
                openai_messages,
                temperature,
                max_tokens,
                response_format,
            )

        try:
            return await _call_with_breaker()
        except RateLimitError as exc:
            retry_after = None
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    retry_after = float(response.headers.get("retry-after", 0.0))
                except (ValueError, TypeError):
                    pass
            raise LLMRateLimitError(
                f"Rate limit exceeded: {exc}",
                provider="OpenRouter",
                model=self.settings.llm_model,
                retry_after=retry_after,
            ) from exc
        except APITimeoutError as exc:
            raise LLMTimeoutError(
                f"Request timed out after {self.settings.llm_timeout_seconds}s: {exc}",
                provider="OpenRouter",
                model=self.settings.llm_model,
            ) from exc
        except APIError as exc:
            response = getattr(exc, "response", None)
            status_code = response.status_code if response is not None else None
            body = getattr(exc, "body", None)
            body_str = str(body) if body is not None else None
            raise LLMProviderError(
                f"Provider API error: {exc}",
                provider="OpenRouter",
                model=self.settings.llm_model,
                status_code=status_code,
                response_body=body_str,
            ) from exc
        except Exception as exc:
            raise LLMError(
                f"Unexpected LLM error: {exc}",
                provider="OpenRouter",
                model=self.settings.llm_model,
            ) from exc

    async def _call_api(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
        response_format: dict[str, Any] | None,
    ) -> LLMResponse:
        from typing import cast

        from openai.types.chat import ChatCompletionMessageParam

        t0 = time.perf_counter()

        extra_headers = {
            "HTTP-Referer": "https://github.com/vishwaksen21/DocTrace-AI",
            "X-Title": "DocTrace AI",
        }

        # Cast to standard SDK types for strict mypy compliance
        api_messages = cast(list[ChatCompletionMessageParam], messages)
        api_response_format = cast(Any, response_format)

        # Issue completion call
        response = await self._client.chat.completions.create(
            model=self.settings.llm_model,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=api_response_format,
            extra_headers=extra_headers,
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0

        choice = response.choices[0]
        content = choice.message.content or ""
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0
        raw_response = response.model_dump()

        return LLMResponse(
            content=content,
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            raw_response=raw_response,
        )

    async def health_check(self) -> bool:
        """Verify OpenRouter connection liveness."""
        try:
            msg = LLMMessage(role="user", content="ping")
            openai_messages = [{"role": msg.role, "content": msg.content}]

            from typing import Any, cast

            api_messages = cast(Any, openai_messages)

            # Use short timeout for quick validation check
            async with AsyncOpenAI(
                base_url=self.settings.openrouter_base_url,
                api_key=self.settings.openrouter_api_key or "placeholder",
                timeout=5.0,
            ) as client:
                await client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=api_messages,
                    max_tokens=1,
                )
            return True
        except Exception:
            return False
