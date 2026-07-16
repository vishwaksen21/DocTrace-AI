"""Redis-backed rate limiter with sliding window algorithm."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as redis

    from app.core.config import Settings


class RateLimiter:
    """Sliding window rate limiter using Redis sorted sets.

    Falls back to in-memory if Redis unavailable.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._redis: redis.Redis | None = None
        self._local_cache: dict[str, list[float]] = {}

    async def initialize(self) -> None:
        """Initialize Redis connection if URL configured."""
        if self.settings.redis_url:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(
                    self.settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
            except Exception:
                self._redis = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()

    async def check_limit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Check if request is within rate limit.

        Args:
            key: Rate limit key (e.g., "ip:192.168.1.1" or "user:123")
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            (allowed: bool, remaining: int)
        """
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"

        if self._redis:
            return await self._check_redis(redis_key, limit, window_seconds, window_start, now)
        return self._check_local(redis_key, limit, window_seconds, window_start, now)

    async def _check_redis(
        self, redis_key: str, limit: int, window_seconds: int, window_start: float, now: float
    ) -> tuple[bool, int]:
        """Check rate limit using Redis sorted set."""
        if self._redis is None:
            return self._check_local(redis_key, limit, window_seconds, window_start, now)

        pipe = self._redis.pipeline()

        # Remove expired entries
        pipe.zremrangebyscore(redis_key, 0, window_start)

        # Count current requests
        pipe.zcard(redis_key)

        # Add current request
        pipe.zadd(redis_key, {str(now): now})

        # Set expiry on key
        pipe.expire(redis_key, window_seconds + 1)

        results = await pipe.execute()
        current_count = results[1]

        if current_count >= limit:
            return False, 0

        return True, limit - current_count

    def _check_local(
        self, key: str, limit: int, window_seconds: int, window_start: float, now: float
    ) -> tuple[bool, int]:
        """In-memory fallback rate limiter."""
        if key not in self._local_cache:
            self._local_cache[key] = []

        # Clean old entries
        self._local_cache[key] = [ts for ts in self._local_cache[key] if ts > window_start]

        if len(self._local_cache[key]) >= limit:
            return False, 0

        self._local_cache[key].append(now)
        return True, limit - len(self._local_cache[key])


async def create_redis_client(settings: Settings) -> redis.Redis | None:
    """Create Redis client if REDIS_URL is configured."""
    if not settings.redis_url:
        return None

    try:
        import redis.asyncio as redis
        client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await client.ping()
        return client
    except Exception:
        return None


async def close_redis_client(client: redis.Redis | None) -> None:
    """Close Redis client."""
    if client:
        await client.close()
