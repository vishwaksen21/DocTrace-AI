"""SQLAlchemy implementation of the Selection repository.

Implements the ``SelectionRepositoryProtocol`` for SQLite and PostgreSQL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.domain.entities import Selection
from app.models.selection import SelectionModel, SelectionNodeModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_entity(model: SelectionModel) -> Selection:
    """Map a SelectionModel ORM object to a Selection domain entity.

    Ensures selected nodes are ordered by ``position_index`` ascending so
    reading order is preserved.
    """
    sorted_nodes = sorted(model.nodes, key=lambda n: n.position_index)
    node_ids = tuple(n.id for n in sorted_nodes)
    return Selection(
        id=model.id,
        version_id=model.version_id,
        node_ids=node_ids,
        created_at=model.created_at,
        name=model.name,
    )


class SqlAlchemySelectionRepository:
    """SQLAlchemy implementation of the Selection repository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an active database session.

        Args:
            session: The AsyncSession to use for database operations.
        """
        self.session = session

    async def get_by_id(self, selection_id: UUID) -> Selection | None:
        """Return the selection with the given UUID, including its node list."""
        stmt = (
            select(SelectionModel)
            .where(SelectionModel.id == selection_id)
            .options(selectinload(SelectionModel.nodes))
        )
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if model is None:
            return None
        return _to_entity(model)

    async def list_for_version(
        self,
        version_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Selection], int]:
        """Return a paginated list of selections for a document version.

        Args:
            version_id: The parent version's UUID.
            offset: Zero-based page offset.
            limit: Maximum items per page.

        Returns:
            ``(selections, total_count)``
        """
        count_stmt = (
            select(func.count())
            .select_from(SelectionModel)
            .where(SelectionModel.version_id == version_id)
        )
        count_res = await self.session.execute(count_stmt)
        total_count = count_res.scalar() or 0

        stmt = (
            select(SelectionModel)
            .where(SelectionModel.version_id == version_id)
            .options(selectinload(SelectionModel.nodes))
            .offset(offset)
            .limit(limit)
            .order_by(SelectionModel.created_at.desc())
        )
        res = await self.session.execute(stmt)
        models = res.scalars().all()

        return [_to_entity(m) for m in models], total_count

    async def create(self, selection: Selection) -> Selection:
        """Persist a new selection (including its node associations).

        The ``selection.node_ids`` list is used to populate the
        ``selection_nodes`` junction table atomically.

        Args:
            selection: The selection to persist.

        Returns:
            The persisted selection with server-assigned fields.
        """
        model = SelectionModel(
            id=selection.id,
            version_id=selection.version_id,
            name=selection.name,
        )
        self.session.add(model)
        await self.session.flush()

        junction_rows = [
            SelectionNodeModel(selection_id=selection.id, node_id=node_id)
            for node_id in selection.node_ids
        ]
        self.session.add_all(junction_rows)
        await self.session.flush()

        # Eager load the nodes relationship for mapping
        stmt = (
            select(SelectionModel)
            .where(SelectionModel.id == selection.id)
            .options(selectinload(SelectionModel.nodes))
        )
        res = await self.session.execute(stmt)
        refreshed_model = res.scalar_one()
        return _to_entity(refreshed_model)

    async def delete(self, selection_id: UUID) -> None:
        """Remove a selection and all its node associations.

        No-op if the selection does not exist.
        """
        model = await self.session.get(SelectionModel, selection_id)
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()

    async def exists(self, selection_id: UUID) -> bool:
        """Return ``True`` if a selection with the given UUID exists."""
        stmt = (
            select(func.count())
            .select_from(SelectionModel)
            .where(SelectionModel.id == selection_id)
        )
        res = await self.session.execute(stmt)
        return (res.scalar() or 0) > 0
