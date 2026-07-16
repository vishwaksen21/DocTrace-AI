"""SQLAlchemy implementation of the Node repository.

Implements the ``NodeRepositoryProtocol`` for SQLite and PostgreSQL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from app.domain.entities import Node
from app.models.node import NodeModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_entity(model: NodeModel) -> Node:
    """Map a NodeModel ORM object to a Node domain entity."""
    return Node(
        id=model.id,
        version_id=model.version_id,
        node_type=model.node_type,
        content=model.content,
        content_hash=model.content_hash,
        position_index=model.position_index,
        path=model.path,
        created_at=model.created_at,
        parent_id=model.parent_id,
        heading_level=model.heading_level,
    )


class SqlAlchemyNodeRepository:
    """SQLAlchemy implementation of the Node repository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an active database session.

        Args:
            session: The AsyncSession to use for database operations.
        """
        self.session = session

    async def get_by_id(self, node_id: UUID) -> Node | None:
        """Return the node with the given UUID, or ``None``."""
        model = await self.session.get(NodeModel, node_id)
        if model is None:
            return None
        return _to_entity(model)

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
        count_stmt = (
            select(func.count())
            .select_from(NodeModel)
            .where(NodeModel.version_id == version_id)
        )
        count_res = await self.session.execute(count_stmt)
        total_count = count_res.scalar() or 0

        stmt = (
            select(NodeModel)
            .where(NodeModel.version_id == version_id)
            .offset(offset)
            .limit(limit)
            .order_by(NodeModel.position_index.asc())
        )
        res = await self.session.execute(stmt)
        models = res.scalars().all()

        return [_to_entity(m) for m in models], total_count

    async def get_children(self, parent_id: UUID) -> list[Node]:
        """Return all direct children of a node in position order.

        Used to reconstruct the heading hierarchy tree.

        Args:
            parent_id: UUID of the parent node.

        Returns:
            All child nodes ordered by ``position_index``.
        """
        stmt = (
            select(NodeModel)
            .where(NodeModel.parent_id == parent_id)
            .order_by(NodeModel.position_index.asc())
        )
        res = await self.session.execute(stmt)
        models = res.scalars().all()
        return [_to_entity(m) for m in models]

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
        stmt = (
            select(NodeModel)
            .where(NodeModel.version_id == version_id)
            .where(NodeModel.content_hash == content_hash)
            .limit(1)
        )
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if model is None:
            return None
        return _to_entity(model)

    async def bulk_create(self, nodes: list[Node]) -> list[Node]:
        """Persist multiple nodes in a single database transaction.

        Using a bulk insert is critical for performance when persisting
        the parsed output of large PDFs (potentially hundreds of nodes).

        Args:
            nodes: The list of nodes to insert.

        Returns:
            The inserted nodes with all database-assigned fields populated.
        """
        models = [
            NodeModel(
                id=n.id,
                version_id=n.version_id,
                parent_id=n.parent_id,
                node_type=n.node_type,
                heading_level=n.heading_level,
                content=n.content,
                content_hash=n.content_hash,
                position_index=n.position_index,
                path=n.path,
            )
            for n in nodes
        ]
        self.session.add_all(models)
        await self.session.flush()
        # SQLAlchemy RETURNING clause populated created_at/updated_at automatically on flush
        return [_to_entity(m) for m in models]

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
        stmt = (
            select(NodeModel)
            .where(NodeModel.version_id == version_id)
            .order_by(NodeModel.position_index.asc())
        )
        res = await self.session.execute(stmt)
        models = res.scalars().all()
        return [_to_entity(m) for m in models]

    async def exists(self, node_id: UUID) -> bool:
        """Return ``True`` if a node with the given UUID exists."""
        stmt = (
            select(func.count())
            .select_from(NodeModel)
            .where(NodeModel.id == node_id)
        )
        res = await self.session.execute(stmt)
        return (res.scalar() or 0) > 0
