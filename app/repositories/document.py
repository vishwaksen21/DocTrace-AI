"""SQLAlchemy implementation of the Document repository.

Implements the ``DocumentRepositoryProtocol`` for SQLite and PostgreSQL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from app.domain.entities import Document
from app.models.document import DocumentModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_entity(model: DocumentModel) -> Document:
    """Map a DocumentModel ORM object to a Document domain entity."""
    return Document(
        id=model.id,
        title=model.title,
        original_filename=model.original_filename,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyDocumentRepository:
    """SQLAlchemy implementation of the Document repository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an active database session.

        Args:
            session: The AsyncSession to use for database operations.
        """
        self.session = session

    async def get_by_id(self, document_id: UUID) -> Document | None:
        """Return the document with the given UUID, or ``None``.

        Args:
            document_id: Primary key of the document.
        """
        model = await self.session.get(DocumentModel, document_id)
        if model is None:
            return None
        return _to_entity(model)

    async def list_paginated(
        self,
        offset: int,
        limit: int,
    ) -> tuple[list[Document], int]:
        """Return a page of documents and the total count.

        Args:
            offset: Zero-based offset into the full result set.
            limit: Maximum number of documents to return.

        Returns:
            ``(documents, total_count)``
        """
        count_stmt = select(func.count()).select_from(DocumentModel)
        count_res = await self.session.execute(count_stmt)
        total_count = count_res.scalar() or 0

        stmt = (
            select(DocumentModel)
            .offset(offset)
            .limit(limit)
            .order_by(DocumentModel.created_at.desc())
        )
        res = await self.session.execute(stmt)
        models = res.scalars().all()

        return [_to_entity(m) for m in models], total_count

    async def create(self, document: Document) -> Document:
        """Persist a new document and return it with server-assigned fields.

        Args:
            document: The document to insert.  The ``id`` field should be
                pre-assigned by the service layer (UUID4).

        Returns:
            The persisted document with ``created_at`` and ``updated_at`` set.
        """
        model = DocumentModel(
            id=document.id,
            title=document.title,
            original_filename=document.original_filename,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def delete(self, document_id: UUID) -> None:
        """Remove a document.  Cascades to versions -> nodes -> selections.

        No-op if the document does not exist.

        Args:
            document_id: Primary key of the document to remove.
        """
        model = await self.session.get(DocumentModel, document_id)
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()

    async def exists(self, document_id: UUID) -> bool:
        """Return ``True`` if a document with the given UUID exists."""
        stmt = (
            select(func.count()).select_from(DocumentModel).where(DocumentModel.id == document_id)
        )
        res = await self.session.execute(stmt)
        return (res.scalar() or 0) > 0

    async def count(self) -> int:
        """Return the total number of documents in the store."""
        stmt = select(func.count()).select_from(DocumentModel)
        res = await self.session.execute(stmt)
        return res.scalar() or 0
