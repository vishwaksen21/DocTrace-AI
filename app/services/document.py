"""Document service layer.

Handles orchestrating Document-related use cases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.domain.entities import Document

if TYPE_CHECKING:
    from app.repositories.interfaces.document import DocumentRepositoryProtocol
    from app.repositories.interfaces.version import VersionRepositoryProtocol


class DocumentService:
    """Service class for managing Documents."""

    def __init__(
        self,
        doc_repo: DocumentRepositoryProtocol,
        version_repo: VersionRepositoryProtocol,
    ) -> None:
        """Initialize the DocumentService.

        Args:
            doc_repo: Concrete implementation of DocumentRepositoryProtocol.
            version_repo: Concrete implementation of VersionRepositoryProtocol.
        """
        self.doc_repo = doc_repo
        self.version_repo = version_repo

    async def create_document(self, title: str, original_filename: str) -> Document:
        """Create and persist a new Document.

        Args:
            title: Human-readable document title.
            original_filename: Auditable name of the source PDF.

        Returns:
            The created Document domain entity.
        """
        now = datetime.now(tz=UTC)
        doc = Document(
            id=uuid4(),
            title=title,
            original_filename=original_filename,
            created_at=now,
            updated_at=now,
        )
        return await self.doc_repo.create(doc)

    async def get_document(self, document_id: UUID) -> Document | None:
        """Retrieve a document by ID.

        Args:
            document_id: UUID of the document.
        """
        return await self.doc_repo.get_by_id(document_id)

    async def list_documents(self, offset: int, limit: int) -> tuple[list[Document], int]:
        """List a paginated page of documents.

        Args:
            offset: Index skip count.
            limit: Maximum items to return.

        Returns:
            Tuple of (documents_list, total_count).
        """
        return await self.doc_repo.list_paginated(offset, limit)

    async def delete_document(self, document_id: UUID) -> None:
        """Delete a document and all associated versions/nodes/selections.

        Args:
            document_id: UUID of the document to remove.
        """
        await self.doc_repo.delete(document_id)
