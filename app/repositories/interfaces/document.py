"""Document repository interface.

NOTE on type annotations
------------------------
``Document`` is imported only under ``TYPE_CHECKING`` (it will be defined
in M3).  With ``from __future__ import annotations``, all annotations
become strings at runtime (PEP 563), so this file works correctly even
before M3 is implemented.  Type checkers (mypy, pyright) will validate
the annotations once M3 exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from app.domain.entities import Document


@runtime_checkable
class DocumentRepositoryProtocol(Protocol):
    """Contract for all operations against the ``documents`` store.

    Implementations may use SQLAlchemy (relational), an in-memory dict
    (tests), or any other backend that satisfies these signatures.
    """

    async def get_by_id(self, document_id: UUID) -> Document | None:
        """Return the document with the given UUID, or ``None``.

        Args:
            document_id: Primary key of the document.
        """
        ...

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
        ...

    async def create(self, document: Document) -> Document:
        """Persist a new document and return it with server-assigned fields.

        Args:
            document: The document to insert.  The ``id`` field should be
                pre-assigned by the service layer (UUID4).

        Returns:
            The persisted document with ``created_at`` and ``updated_at`` set.
        """
        ...

    async def delete(self, document_id: UUID) -> None:
        """Remove a document.  Cascades to versions → nodes → selections.

        No-op if the document does not exist.

        Args:
            document_id: Primary key of the document to remove.
        """
        ...

    async def exists(self, document_id: UUID) -> bool:
        """Return ``True`` if a document with the given UUID exists."""
        ...

    async def count(self) -> int:
        """Return the total number of documents in the store."""
        ...
