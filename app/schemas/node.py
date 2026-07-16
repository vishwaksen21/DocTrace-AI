"""Node schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import NodeType


class NodeResponse(BaseModel):
    """Response representing a structural parsed document node."""

    model_config = {"from_attributes": True}

    id: UUID
    version_id: UUID
    parent_id: UUID | None
    node_type: NodeType
    heading_level: int | None
    content: str
    content_hash: str
    position_index: int
    path: str
    created_at: datetime
