"""LLM client package.

Contains:
    base.py          Protocol and value types for LLM interaction
    openrouter.py    OpenRouter implementation (added in M10)

Design rationale
----------------
The LLM client is hidden behind a ``Protocol`` (structural interface).
Any class that implements ``complete(messages) → LLMResponse`` satisfies
the contract, with no explicit inheritance required.

Swapping providers (OpenRouter → OpenAI → Groq) requires:
    1. Changing ``OPENROUTER_BASE_URL`` and ``LLM_MODEL`` env vars, or
    2. Providing an alternative ``LLMClientProtocol`` implementation

Neither change touches the service layer.
"""
