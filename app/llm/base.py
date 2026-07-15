"""LLM client protocol and value types.

This module defines:
    - ``LLMMessage``         A single message in the LLM conversation
    - ``LLMResponse``        The parsed response from the LLM
    - ``LLMClientProtocol``  Structural interface all LLM clients must satisfy
    - LLM exception hierarchy (``LLMError``, ``LLMTimeoutError``,
      ``LLMRateLimitError``, ``LLMValidationError``, ``LLMProviderError``)

Provider-agnosticism
--------------------
The service layer depends only on ``LLMClientProtocol``.  Any class with:

    async def complete(messages, *, temperature, ...) -> LLMResponse

satisfies the protocol — no explicit inheritance needed.

To switch LLM providers, change:
    - ``OPENROUTER_BASE_URL`` env var
    - ``LLM_MODEL`` env var

Or inject a different ``LLMClientProtocol`` implementation via
FastAPI's dependency system (useful for testing with a mock).

Concrete implementation
-----------------------
The OpenRouter implementation is in ``app/llm/openrouter.py`` (added M10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# ── LLM Exception Hierarchy ─────────────────────────────────────────────────────
#
# All LLM-related exceptions inherit from ``LLMError`` so callers can catch
# any LLM failure with a single ``except LLMError`` clause.  Specific subclasses
# allow differentiated handling (retry on timeout/rate-limit, fail fast on validation).


class LLMError(Exception):
    """Base class for all LLM-related errors."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model


class LLMTimeoutError(LLMError):
    """Request exceeded the configured timeout."""


class LLMRateLimitError(LLMError):
    """Provider returned 429 (rate limited); retries exhausted.

    Attributes:
        retry_after: Seconds to wait before retrying, if provided by the provider.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider, model=model)
        self.retry_after = retry_after


class LLMValidationError(LLMError):
    """Request parameters failed validation (e.g., invalid model, bad message format)."""


class LLMProviderError(LLMError):
    """Any other non-retryable provider error (5xx, auth failure, quota exceeded)."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message, provider=provider, model=model)
        self.status_code = status_code
        self.response_body = response_body


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """A single message in an LLM conversation.

    Attributes:
        role: The speaker role — ``"system"``, ``"user"``, or ``"assistant"``.
        content: The raw text content of the message.
    """

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """The parsed response from an LLM API call.

    Attributes:
        content: The text content of the model's reply.
        model: The exact model identifier returned by the provider.
        prompt_tokens: Number of tokens consumed by the input messages.
        completion_tokens: Number of tokens in the model's reply.
        duration_ms: Total round-trip time for the API call in milliseconds.
        raw_response: The full provider response payload, stored for
            debugging and re-processing without another API call.
    """

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    duration_ms: float
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """Return the sum of prompt and completion tokens."""
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Structural interface for all LLM provider clients.

    Any class that implements ``complete`` and exposes ``model`` satisfies
    this protocol — no explicit inheritance required.

    This design means:
    - Tests can use a plain Python dataclass or ``MagicMock`` as a client
    - Providers (OpenRouter, OpenAI, Groq) are interchangeable at injection time
    - The service layer never imports a concrete client class

    The ``@runtime_checkable`` decorator enables ``isinstance(obj, LLMClientProtocol)``
    checks in tests and dependency validation code.
    """

    @property
    def model(self) -> str:
        """The model identifier this client is configured to use."""
        ...

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Send a completion request to the LLM and return the parsed response.

        Args:
            messages: Conversation history in chronological order.
                The last message is typically from the ``"user"`` role.
            temperature: Sampling temperature (0.0 = deterministic,
                1.0 = creative).  Default is low for structured output.
            max_tokens: Maximum tokens in the completion.  ``None`` means
                use the provider's default.
            response_format: Provider-specific response format hint
                (e.g., ``{"type": "json_object"}`` for JSON mode).

        Returns:
            A parsed ``LLMResponse`` with content, token counts, and timing.

        Raises:
            LLMTimeoutError: Request exceeded the configured timeout.
            LLMRateLimitError: Provider returned 429; retries exhausted.
            LLMProviderError: Any other non-retryable provider error.
        """
        ...

    async def health_check(self) -> bool:
        """Verify the LLM provider is reachable.

        Returns:
            ``True`` if the provider responds within the configured timeout.
            ``False`` on any connectivity or authentication error.
        """
        ...
