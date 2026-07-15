"""Version repository interface.

See ``document.py`` for the note on ``TYPE_CHECKING`` and PEP 563
forward references used throughout this package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from app.domain.entities import Version


@runtime_checkable
class VersionRepositoryProtocol(Protocol):
    """Contract for all operations against the ``versions`` store."""

    async def get_by_id(self, version_id: UUID) -> Version | None:
        """Return the version with the given UUID, or ``None``."""
        ...

    async def list_for_document(
        self,
        document_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Version], int]:
        """Return a paginated list of versions for a document.

        Versions are ordered by ``version_number`` ascending (oldest first).

        Args:
            document_id: The parent document's UUID.
            offset: Zero-based page offset.
            limit: Maximum items per page.

        Returns:
            ``(versions, total_count)``
        """
        ...

    async def get_latest_for_document(self, document_id: UUID) -> Version | None:
        """Return the highest-numbered version for the document, or ``None``.

        Used by the default diff strategy to compare a new upload against
        its immediate predecessor.
        """
        ...

    async def get_previous_version(
        self,
        document_id: UUID,
        version_number: int,
    ) -> Version | None:
        """Return the version immediately before ``version_number``, or ``None``.

        Used by the versioning diff engine.  When ``version_number`` is 1,
        there is no previous version and this returns ``None``.

        Args:
            document_id: The parent document's UUID.
            version_number: The reference version number (1-indexed).
        """
        ...

    async def get_next_version_number(self, document_id: UUID) -> int:
        """Return the next sequential version number for a document.

        Starts at 1 for a new document.  Implementations must ensure
        this is atomic to prevent duplicate version numbers under concurrent
        uploads.

        Args:
            document_id: The parent document's UUID.

        Returns:
            The next version number (``max_existing + 1`` or ``1``).
        """
        ...

    async def create(self, version: Version) -> Version:
        """Persist a new version record and return it with server fields set."""
        ...

    async def update_status(
        self,
        version_id: UUID,
        status: str,
    ) -> Version | None:
        """Update the processing status of a version.

        Used by ``BackgroundTasks`` to mark a version as ``"ready"`` after
        parsing completes, or ``"failed"`` if parsing raises an error.

        Args:
            version_id: The version's UUID.
            status: One of ``"processing"``, ``"ready"``, ``"failed"``.

        Returns:
            The updated version, or ``None`` if not found.
        """
        ...

    async def exists(self, version_id: UUID) -> bool:
        """Return ``True`` if a version with the given UUID exists."""
        ...
