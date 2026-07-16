"""SQLAlchemy implementation of the Version repository.

Implements the ``VersionRepositoryProtocol`` for SQLite and PostgreSQL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from app.domain.entities import Version
from app.domain.enums import VersionStatus
from app.models.document import DocumentModel
from app.models.version import VersionModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_entity(model: VersionModel) -> Version:
    """Map a VersionModel ORM object to a Version domain entity."""
    return Version(
        id=model.id,
        document_id=model.document_id,
        version_number=model.version_number,
        upload_filename=model.upload_filename,
        status=model.status,
        created_at=model.created_at,
        error_message=model.error_message,
    )


class SqlAlchemyVersionRepository:
    """SQLAlchemy implementation of the Version repository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an active database session.

        Args:
            session: The AsyncSession to use for database operations.
        """
        self.session = session

    async def get_by_id(self, version_id: UUID) -> Version | None:
        """Return the version with the given UUID, or ``None``."""
        model = await self.session.get(VersionModel, version_id)
        if model is None:
            return None
        return _to_entity(model)

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
        count_stmt = (
            select(func.count())
            .select_from(VersionModel)
            .where(VersionModel.document_id == document_id)
        )
        count_res = await self.session.execute(count_stmt)
        total_count = count_res.scalar() or 0

        stmt = (
            select(VersionModel)
            .where(VersionModel.document_id == document_id)
            .offset(offset)
            .limit(limit)
            .order_by(VersionModel.version_number.asc())
        )
        res = await self.session.execute(stmt)
        models = res.scalars().all()

        return [_to_entity(m) for m in models], total_count

    async def get_latest_for_document(self, document_id: UUID) -> Version | None:
        """Return the highest-numbered version for the document, or ``None``.

        Used by the default diff strategy to compare a new upload against
        its immediate predecessor.
        """
        stmt = (
            select(VersionModel)
            .where(VersionModel.document_id == document_id)
            .order_by(VersionModel.version_number.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if model is None:
            return None
        return _to_entity(model)

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
        stmt = (
            select(VersionModel)
            .where(VersionModel.document_id == document_id)
            .where(VersionModel.version_number < version_number)
            .order_by(VersionModel.version_number.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if model is None:
            return None
        return _to_entity(model)

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
        # Lock the parent document row to coordinate concurrent uploads (ignored in SQLite)
        lock_stmt = (
            select(DocumentModel.id).where(DocumentModel.id == document_id).with_for_update()
        )
        await self.session.execute(lock_stmt)

        stmt = select(func.max(VersionModel.version_number)).where(
            VersionModel.document_id == document_id
        )
        res = await self.session.execute(stmt)
        val = res.scalar()
        if val is None:
            return 1
        return val + 1

    async def create(self, version: Version) -> Version:
        """Persist a new version record and return it with server fields set."""
        model = VersionModel(
            id=version.id,
            document_id=version.document_id,
            version_number=version.version_number,
            upload_filename=version.upload_filename,
            status=version.status,
            error_message=version.error_message,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def update_status(
        self,
        version_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> Version | None:
        """Update the processing status and optional error message of a version.

        Used by ``BackgroundTasks`` to mark a version as ``"ready"`` after
        parsing completes, or ``"failed"`` if parsing raises an error.

        Args:
            version_id: The version's UUID.
            status: One of ``"processing"``, ``"ready"``, ``"failed"``.
            error_message: Optional error details.

        Returns:
            The updated version, or ``None`` if not found.
        """
        model = await self.session.get(VersionModel, version_id)
        if model is None:
            return None
        model.status = VersionStatus(status)
        if error_message is not None:
            model.error_message = error_message
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def exists(self, version_id: UUID) -> bool:
        """Return ``True`` if a version with the given UUID exists."""
        stmt = select(func.count()).select_from(VersionModel).where(VersionModel.id == version_id)
        res = await self.session.execute(stmt)
        return (res.scalar() or 0) > 0
