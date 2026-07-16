"""Document schemas."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.schemas.version import VersionResponse


class DocumentCreate(BaseModel):
    """Payload to create a document."""

    title: str = Field(..., min_length=1, max_length=500, description="Document title")


class DocumentResponse(BaseModel):
    """Response representing a document."""

    model_config = {"from_attributes": True}

    id: UUID
    title: str
    original_filename: str
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    """Response returned upon uploading a new document."""

    document: DocumentResponse
    version: VersionResponse
