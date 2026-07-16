"""Authentication core: JWT tokens, password hashing, token validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

if TYPE_CHECKING:
    from app.core.config import Settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass(frozen=True, slots=True)
class TokenData:
    """Decoded JWT token payload."""

    sub: UUID  # User ID
    email: str
    roles: tuple[str, ...] = ()
    exp: datetime | None = None
    iat: datetime | None = None
    jti: str | None = None  # Token ID for revocation


@dataclass(frozen=True, slots=True)
class User:
    """User domain entity."""

    id: UUID
    email: str
    hashed_password: str
    full_name: str | None = None
    is_active: bool = True
    roles: tuple[str, ...] = ()
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(UTC))


def _dt_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO format string for JWT payload."""
    return dt.isoformat()


def create_access_token(
    data: dict[str, str],
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": _dt_to_iso(expire), "iat": _dt_to_iso(now), "jti": uuid4().hex})
    return cast(str, jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm))


def create_refresh_token(
    data: dict[str, str],
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token (longer expiry)."""
    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(days=settings.refresh_token_expire_days))
    to_encode.update(
        {
            "exp": _dt_to_iso(expire),
            "iat": _dt_to_iso(now),
            "jti": uuid4().hex,
            "type": "refresh",
        }
    )
    return cast(str, jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm))


def decode_token(token: str, settings: Settings) -> TokenData:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise ValueError("Invalid token") from exc

    return TokenData(
        sub=UUID(payload.get("sub")),
        email=payload.get("email", ""),
        roles=tuple(payload.get("roles", [])),
        exp=datetime.fromisoformat(payload["exp"]) if payload.get("exp") else None,
        iat=datetime.fromisoformat(payload["iat"]) if payload.get("iat") else None,
        jti=payload.get("jti"),
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return cast(bool, pwd_context.verify(plain_password, hashed_password))


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return cast(str, pwd_context.hash(password))


def create_token_payload(user: User) -> dict[str, str]:
    """Create the standard token payload for a user."""
    return {
        "sub": str(user.id),
        "email": user.email,
        "roles": " ".join(user.roles),
    }
