"""Node repository interface.

See ``document.py`` for the note on ``TYPE_CHECKING`` and PEP 563
forward references used throughout this package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from app.domain.entities import Node


@runtime_checkable
class NodeRepositoryProtocol(Protocol):
    """Contract for all operations against the ``nodes`` store."""

    async def get_by_id(self, node_id: UUID) -> Node | None:
        """Return the node with the given UUID, or ``None``."""
        ...

    async def list_for_version(
        self,
        version_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Node], int]:
        """Return a paginated list of nodes for a version.

        Nodes are ordered by ``position_index`` ascending to preserve the
        original document reading order.

        Args:
            version_id: The parent version's UUID.
            offset: Zero-based page offset.
            limit: Maximum items per page.

        Returns:
            ``(nodes, total_count)``
        """
        ...

    async def get_children(self, parent_id: UUID) -> list[Node]:
        """Return all direct children of a node in position order.

        Used to reconstruct the heading hierarchy tree.

        Args:
            parent_id: UUID of the parent node.

        Returns:
            All child nodes ordered by ``position_index``.
        """
        ...

    async def get_by_content_hash(
        self,
        version_id: UUID,
        content_hash: str,
    ) -> Node | None:
        """Return a node matching a content hash within a specific version.

        Used by the diff engine to detect unchanged nodes across versions.

        Args:
            version_id: The version to search within.
            content_hash: SHA-256 hex digest of the normalised content.

        Returns:
            The matching node, or ``None`` if no match exists.
        """
        ...

    async def bulk_create(self, nodes: list[Node]) -> list[Node]:
        """Persist multiple nodes in a single database transaction.

        Using a bulk insert is critical for performance when persisting
        the parsed output of large PDFs (potentially hundreds of nodes).

        Args:
            nodes: The list of nodes to insert.

        Returns:
            The inserted nodes with all database-assigned fields populated.
        """
        ...

    async def get_nodes_for_diff(
        self,
        version_id: UUID,
    ) -> list[Node]:
        """Return ALL nodes for a version in position order.

        Returns the full list (not paginated) because the diff algorithm
        must have visibility over the entire node set to compute the
        position-anchored matching.

        Args:
            version_id: The version's UUID.

        Returns:
            All nodes for the version, ordered by ``position_index``.
        """
        ...

    async def exists(self, node_id: UUID) -> bool:
        """Return ``True`` if a node with the given UUID exists."""
        ...
