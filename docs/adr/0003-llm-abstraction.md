# ADR 0003: Provider-Agnostic LLM Client via Protocol

## Status
Accepted

## Context
The application needs to call LLMs for QA test case generation. The team wants to:
- Support multiple providers (OpenRouter, OpenAI, Groq, Anthropic, etc.)
- Avoid vendor lock-in
- Enable testing with fakes/mocks
- Switch providers via configuration only

## Decision
Define an **LLM Client Protocol** (`app/llm/base.py`) and implement concrete clients per provider.

### Protocol
```python
class LLMClientProtocol(Protocol):
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: type[BaseModel] | None = None,
    ) -> LLMResponse: ...
```

### Configuration
Two environment variables control the provider:
```bash
# OpenRouter (default)
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=google/gemini-2.5-flash

# OpenAI
OPENROUTER_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Groq
OPENROUTER_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-70b-versatile
```

### Implementation
- `app/llm/openrouter.py` — OpenAI-compatible client using `openai.AsyncOpenAI`
- `app/llm/response_validator.py` — Validates structured output against Pydantic models
- `app/llm/prompts.py` — Prompt templates for QA generation

### Dependency Injection
```python
# app/api/deps.py
def get_llm_client() -> LLMClientProtocol:
    return OpenRouterClient(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
```

Tests override with a fake client implementing the protocol.

## Consequences
### Positive
- Zero code changes to switch providers
- Easy to test (fake implementation in ~50 lines)
- Structured output validation via Pydantic
- Retry/timeout logic centralized in base client

### Negative
- Limited to OpenAI-compatible APIs (no native Anthropic/Vertex support without adapter)
- Must handle provider-specific quirks in the client implementation

## Future Work
- Add `AnthropicClient` for native Claude support
- Add fallback/spillover across multiple providers