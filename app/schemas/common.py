"""Common Pydantic schemas for pagination and standardized error envelopes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized envelope for all list endpoints."""

    items: list[T] = Field(description="Page elements list")
    total: int = Field(description="Total count of matches")
    offset: int = Field(description="Skip offset value")
    limit: int = Field(description="Max page limit value")


class ErrorResponse(BaseModel):
    """Standardized API error envelope matching DomainException Taxonomy."""

    error: str = Field(description="Machine-readable error category code")
    message: str = Field(description="Human-readable warning details")
    details: dict[str, Any] = Field(default_factory=dict, description="Diagnostic payload contexts")
    request_id: str = Field(description="Correlation request tracing trace ID")
