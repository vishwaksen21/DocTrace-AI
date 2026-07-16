"""Authentication and authorization core.

Provides JWT token handling, password hashing, user identity management,
Redis-backed rate limiting, and FastAPI dependencies.
"""

from __future__ import annotations

from app.auth.auth import (
    TokenData,
    User,
    create_access_token,
    create_refresh_token,
    create_token_payload,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.auth.dependencies import (
    close_rate_limiter,
    get_current_user,
    get_optional_user,
    get_rate_limiter,
    init_rate_limiter,
    rate_limit_dependency,
    require_admin,
    require_user,
)
from app.auth.rate_limiter import RateLimiter, close_redis_client, create_redis_client

__all__ = [
    "RateLimiter",
    "TokenData",
    "User",
    "close_rate_limiter",
    "close_redis_client",
    "create_access_token",
    "create_redis_client",
    "create_refresh_token",
    "create_token_payload",
    "decode_token",
    "get_current_user",
    "get_optional_user",
    "get_password_hash",
    "get_rate_limiter",
    "init_rate_limiter",
    "rate_limit_dependency",
    "require_admin",
    "require_user",
    "verify_password",
]
