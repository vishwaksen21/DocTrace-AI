"""Selection and generation repository interfaces.

See ``document.py`` for the note on ``TYPE_CHECKING`` and PEP 563
forward references used throughout this package.

Both interfaces are in the same file because ``Selection`` and
``GenerationResult`` are closely coupled:  a generation is always
associated with a selection, and they are typically fetched together.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from app.domain.entities import GenerationResult, Selection


@runtime_checkable
class SelectionRepositoryProtocol(Protocol):
    """Contract for all operations against the ``selections`` store."""

    async def get_by_id(self, selection_id: UUID) -> Selection | None:
        """Return the selection with the given UUID, including its node list."""
        ...

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
        ...

    async def create(self, selection: Selection) -> Selection:
        """Persist a new selection (including its node associations).

        The ``selection.node_ids`` list is used to populate the
        ``selection_nodes`` junction table atomically.

        Args:
            selection: The selection to persist.

        Returns:
            The persisted selection with server-assigned fields.
        """
        ...

    async def delete(self, selection_id: UUID) -> None:
        """Remove a selection and all its node associations.

        No-op if the selection does not exist.
        """
        ...

    async def exists(self, selection_id: UUID) -> bool:
        """Return ``True`` if a selection with the given UUID exists."""
        ...


@runtime_checkable
class GenerationRepositoryProtocol(Protocol):
    """Contract for all operations against the MongoDB ``generation_results`` collection.

    Implementations operate against MongoDB (via Motor) rather than SQLAlchemy,
    because LLM output is schema-flexible and benefits from document storage.
    """

    async def get_by_id(self, generation_id: str) -> GenerationResult | None:
        """Return the generation result with the given MongoDB ObjectId string."""
        ...

    async def list_for_selection(
        self,
        selection_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[GenerationResult], int]:
        """Return a paginated list of generation results for a selection.

        Ordered by ``created_at`` descending (newest first).

        Args:
            selection_id: The parent selection's UUID.
            offset: Zero-based page offset.
            limit: Maximum items per page.

        Returns:
            ``(results, total_count)``
        """
        ...

    async def create(self, result: GenerationResult) -> GenerationResult:
        """Persist a new generation result in MongoDB.

        Args:
            result: The result to store.  The MongoDB ``_id`` is assigned
                by the driver; ``result.id`` may be ``None`` before save.

        Returns:
            The persisted result with ``id`` set to the assigned ObjectId string.
        """
        ...

    async def update_status(
        self,
        generation_id: str,
        status: str,
        updates: dict[str, Any] | None = None,
    ) -> GenerationResult | None:
        """Partially update a generation result's status and optional fields.

        Used by ``BackgroundTasks`` to update status from ``"processing"``
        to ``"success"`` or ``"failed"`` after the LLM call completes.

        Args:
            generation_id: The MongoDB ObjectId string of the result.
            status: New status value (``"processing"``, ``"success"``,
                ``"failed"``, ``"partial"``).
            updates: Optional additional fields to merge into the document.

        Returns:
            The updated result, or ``None`` if not found.
        """
        ...
