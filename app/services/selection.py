"""Selection service layer.

Orchestrates Node selection business logic and validation rules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.domain.entities import Selection
from app.domain.enums import VersionStatus
from app.domain.exceptions import (
    CrossVersionSelectionError,
    EmptySelectionError,
    NodeNotFoundError,
    SelectionNotFoundError,
    VersionNotFoundError,
    VersionNotReadyError,
)

if TYPE_CHECKING:
    from app.repositories.interfaces.node import NodeRepositoryProtocol
    from app.repositories.interfaces.selection import SelectionRepositoryProtocol
    from app.repositories.interfaces.version import VersionRepositoryProtocol


class SelectionService:
    """Service class for managing selections of parsed nodes."""

    def __init__(
        self,
        selection_repo: SelectionRepositoryProtocol,
        version_repo: VersionRepositoryProtocol,
        node_repo: NodeRepositoryProtocol,
    ) -> None:
        """Initialize the SelectionService.

        Args:
            selection_repo: Concrete SelectionRepositoryProtocol.
            version_repo: Concrete VersionRepositoryProtocol.
            node_repo: Concrete NodeRepositoryProtocol.
        """
        self.selection_repo = selection_repo
        self.version_repo = version_repo
        self.node_repo = node_repo

    async def get_selection(self, selection_id: UUID) -> Selection | None:
        """Retrieve a Selection by UUID.

        Args:
            selection_id: UUID of the selection.
        """
        return await self.selection_repo.get_by_id(selection_id)

    async def get_selection_or_raise(self, selection_id: UUID) -> Selection:
        """Retrieve a Selection or raise SelectionNotFoundError.

        Args:
            selection_id: UUID of the selection.
        """
        sel = await self.selection_repo.get_by_id(selection_id)
        if sel is None:
            raise SelectionNotFoundError(selection_id)
        return sel

    async def list_selections(
        self,
        version_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Selection], int]:
        """List paginated selections associated with a specific version.

        Args:
            version_id: Parent version UUID.
            offset: Page offset.
            limit: Return limit.
        """
        if not await self.version_repo.exists(version_id):
            raise VersionNotFoundError(version_id)
        return await self.selection_repo.list_for_version(version_id, offset, limit)

    async def create_selection(
        self,
        version_id: UUID,
        node_ids: list[UUID],
        name: str | None = None,
    ) -> Selection:
        """Create and persist a new node selection.

        Validates selection readiness and ensures all nodes exist and belong
        to the same version.

        Args:
            version_id: The target document version UUID.
            node_ids: Non-empty list of selected node UUIDs.
            name: Optional user-provided label.
        """
        if not node_ids:
            raise EmptySelectionError()

        # 1. Verify parent version exists and is READY
        ver = await self.version_repo.get_by_id(version_id)
        if ver is None:
            raise VersionNotFoundError(version_id)
        if ver.status != VersionStatus.READY:
            raise VersionNotReadyError(version_id, str(ver.status))

        # 2. Validate all nodes exist and belong to the correct version
        distinct_versions: set[UUID] = set()
        for node_id in node_ids:
            node = await self.node_repo.get_by_id(node_id)
            if node is None:
                raise NodeNotFoundError(node_id)
            if node.version_id != version_id:
                distinct_versions.add(node.version_id)

        if distinct_versions:
            # Nodes from multiple different versions found
            distinct_versions.add(version_id)
            raise CrossVersionSelectionError(distinct_versions)

        # 3. Persist selection entity
        sel = Selection(
            id=uuid4(),
            version_id=version_id,
            node_ids=tuple(node_ids),
            created_at=datetime.now(tz=UTC),
            name=name,
        )
        return await self.selection_repo.create(sel)

    async def delete_selection(self, selection_id: UUID) -> None:
        """Remove a selection and its node junction associations.

        Args:
            selection_id: UUID of the selection.
        """
        await self.selection_repo.delete(selection_id)
