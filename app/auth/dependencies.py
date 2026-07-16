"""JWT authentication middleware and dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.auth import TokenData, decode_token
from app.auth.rate_limiter import RateLimiter
from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    pass

security = HTTPBearer(auto_error=False)


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(get_settings())
    return _rate_limiter


async def init_rate_limiter() -> None:
    """Initialize rate limiter on startup."""
    rate_limiter = get_rate_limiter()
    await rate_limiter.initialize()


async def close_rate_limiter() -> None:
    """Close rate limiter on shutdown."""
    global _rate_limiter
    if _rate_limiter:
        await _rate_limiter.close()
        _rate_limiter = None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> TokenData:
    """Extract and validate JWT token from Authorization header.

    Raises:
        HTTPException: 401 if token missing, invalid, or expired
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token_data = decode_token(credentials.credentials, settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Attach to request state for downstream use
    request.state.user = token_data
    return token_data


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> TokenData | None:
    """Get current user if authenticated, otherwise None (for optional auth endpoints)."""
    if credentials is None:
        return None

    try:
        token_data = decode_token(credentials.credentials, settings)
        request.state.user = token_data
        return token_data
    except ValueError:
        return None


async def rate_limit_dependency(
    request: Request,
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    """Enforce rate limiting per IP."""
    if not rate_limiter.settings.rate_limit_enabled:
        return

    client_ip = request.client.host if request.client else "unknown"
    key = f"ip:{client_ip}"

    allowed, remaining = await rate_limiter.check_limit(
        key,
        rate_limiter.settings.rate_limit_requests,
        rate_limiter.settings.rate_limit_window_seconds,
    )

    request.state.rate_limit_remaining = remaining

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RateLimitExceeded",
                "message": (
                    f"Rate limit exceeded. Maximum {rate_limiter.settings.rate_limit_requests} "
                    f"requests per {rate_limiter.settings.rate_limit_window_seconds} seconds."
                ),
            },
            headers={"Retry-After": str(rate_limiter.settings.rate_limit_window_seconds)},
        )


def require_roles(*required_roles: str) -> Callable[[TokenData], TokenData]:
    """Dependency that requires specific roles."""

    async def role_checker(user: TokenData = Depends(get_current_user)) -> TokenData:
        if not any(role in user.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return role_checker  # type: ignore[return-value]


# Admin-only dependency
require_admin = require_roles("admin")

# Any authenticated user
require_user = require_roles("user", "admin")
