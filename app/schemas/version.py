"""Version schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import VersionStatus


class VersionResponse(BaseModel):
    """Response representing a document version."""

    model_config = {"from_attributes": True}

    id: UUID
    document_id: UUID
    version_number: int
    upload_filename: str
    status: VersionStatus
    error_message: str | None
    created_at: datetime


class NodeDiffResponse(BaseModel):
    """Response representing a single node diff action."""

    model_config = {"from_attributes": True}

    node_id: UUID | None = None
    old_node_id: UUID | None = None
    new_node_id: UUID | None = None
    status: str
    content_changed: bool
    old_path: str | None = None
    new_path: str | None = None
    old_position_index: int | None = None
    new_position_index: int | None = None
