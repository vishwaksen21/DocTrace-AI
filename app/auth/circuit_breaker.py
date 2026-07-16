"""Circuit breaker for LLM calls."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes before closing from half-open
    timeout_seconds: float = 30.0  # Time before half-open
    excluded_exceptions: tuple[type[BaseException], ...] = ()  # Don't count these


@dataclass
class CircuitBreaker(Generic[T]):
    """Circuit breaker implementation.

    Usage:
        breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5, timeout_seconds=30))
        result = await breaker.call(llm_client.complete, messages)
    """

    config: CircuitBreakerConfig
    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
    _success_count: int = 0
    _last_failure_time: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.config.timeout_seconds:
                    logger.info("Circuit breaker entering HALF_OPEN state")
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker OPEN. Retry after {self.config.timeout_seconds}s"
                    )

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except self.config.excluded_exceptions:
            raise
        except Exception:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    logger.info("Circuit breaker CLOSED after successful recovery")
                    self._state = CircuitState.CLOSED
                    self._success_count = 0

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            self._success_count = 0

            if self._state == CircuitState.HALF_OPEN:
                logger.warning("Circuit breaker reopened after failure in HALF_OPEN")
                self._state = CircuitState.OPEN
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    logger.warning(
                        "Circuit breaker OPENED after %d failures",
                        self._failure_count,
                    )
                    self._state = CircuitState.OPEN


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


# Pre-configured breakers for common LLM providers
OPENAI_BREAKER: CircuitBreaker[Any] = CircuitBreaker(
    CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=2,
        timeout_seconds=60,
        excluded_exceptions=(asyncio.CancelledError,),
    )
)

OPENROUTER_BREAKER: CircuitBreaker[Any] = CircuitBreaker(
    CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=2,
        timeout_seconds=60,
        excluded_exceptions=(asyncio.CancelledError,),
    )
)
