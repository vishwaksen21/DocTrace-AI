"""LLM client package.

Contains:
    base.py          Protocol and value types for LLM interaction
    openrouter.py    OpenRouter implementation using AsyncOpenAI

Design rationale
----------------
The LLM client is hidden behind a ``Protocol`` (structural interface).
Any class that implements ``complete(messages) -> LLMResponse`` satisfies
the contract, with no explicit inheritance required.

Swapping providers (OpenRouter -> OpenAI -> Groq) requires:
    1. Changing ``OPENROUTER_BASE_URL`` and ``LLM_MODEL`` env vars, or
    2. Providing an alternative ``LLMClientProtocol`` implementation

Neither change touches the service layer.
"""

from __future__ import annotations

from app.llm.base import (
    LLMClientProtocol,
    LLMError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    LLMValidationError,
)
from app.llm.openrouter import OpenRouterClient

__all__ = [
    "LLMClientProtocol",
    "LLMError",
    "LLMMessage",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMTimeoutError",
    "LLMValidationError",
    "OpenRouterClient",
]
