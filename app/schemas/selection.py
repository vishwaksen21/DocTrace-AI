"""Selection schemas."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.schemas.node import NodeResponse


class SelectionCreate(BaseModel):
    """Payload to create a node selection."""

    version_id: UUID = Field(..., description="Document version UUID")
    node_ids: list[UUID] = Field(
        ..., min_length=1, description="List of node UUIDs in the selection"
    )
    name: str | None = Field(default=None, max_length=200, description="Optional label")


class SelectionResponse(BaseModel):
    """Response representing a node selection."""

    model_config = {"from_attributes": True}

    id: UUID
    version_id: UUID
    node_ids: list[UUID]
    created_at: datetime
    name: str | None


class SelectionWithNodesResponse(SelectionResponse):
    """Response representing a selection and its nodes."""

    nodes: list[NodeResponse]
