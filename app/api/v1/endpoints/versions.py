"""Version comparison and nodes query endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_version_service
from app.schemas import (
    NodeDiffResponse,
    NodeResponse,
    PaginatedResponse,
)
from app.services import VersionService

router = APIRouter()


@router.get(
    "/{version_id}/nodes",
    response_model=PaginatedResponse[NodeResponse],
    summary="Get version nodes",
    description="Retrieve a paginated page of structural nodes parsed for a version.",
)
async def list_version_nodes(
    version_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    ver_service: VersionService = Depends(get_version_service),
) -> PaginatedResponse[NodeResponse]:
    items, total = await ver_service.list_nodes(
        version_id=version_id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(
        items=[NodeResponse.model_validate(x) for x in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{version_id}/diff",
    response_model=list[NodeDiffResponse],
    summary="Diff version",
    description=(
        "Compute the structural diff of this version against a base comparison version. "
        "If compare_to_version_id is not specified, diffs against the preceding version sequence."
    ),
)
async def diff_version(
    version_id: UUID,
    compare_to_version_id: UUID | None = Query(default=None),
    ver_service: VersionService = Depends(get_version_service),
) -> list[NodeDiffResponse]:
    from app.domain.enums import DiffStatus

    diffs = await ver_service.compare_versions(
        new_version_id=version_id,
        old_version_id=compare_to_version_id,
    )
    return [
        NodeDiffResponse(
            node_id=x.node.id,
            old_node_id=x.node.id if x.status != DiffStatus.ADDED else None,
            new_node_id=x.node.id if x.status != DiffStatus.DELETED else None,
            status=x.status.value,
            content_changed=x.status == DiffStatus.MODIFIED,
            old_path=x.node.path if x.status != DiffStatus.ADDED else None,
            new_path=x.node.path if x.status != DiffStatus.DELETED else None,
            old_position_index=x.old_position_index,
            new_position_index=x.new_position_index,
        )
        for x in diffs
    ]
