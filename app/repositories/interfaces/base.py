"""Generic base repository Protocol.

Defines the minimal CRUD contract that all entity-specific repositories
must satisfy.  Domain-specific interfaces extend this with additional
query methods relevant to their aggregate.

Generic type parameter
----------------------
``EntityT`` is a type variable bound to the entity type managed by the
repository.  Concrete Protocols (e.g., ``DocumentRepositoryProtocol``)
use explicit types rather than this generic base to keep method signatures
readable and IDE-friendly.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable
from uuid import UUID

EntityT = TypeVar("EntityT")


@runtime_checkable
class BaseRepositoryProtocol(Protocol[EntityT]):
    """Minimal CRUD interface for a single aggregate type.

    All repository implementations — whether SQLAlchemy, in-memory stubs,
    or read-model projections — must satisfy this interface.

    Type parameter:
        EntityT: The domain entity type managed by this repository.
    """

    async def get_by_id(self, entity_id: UUID) -> EntityT | None:
        """Return the entity with the given UUID, or ``None`` if not found.

        Args:
            entity_id: The primary key of the entity.

        Returns:
            The entity, or ``None``.
        """
        ...

    async def list_paginated(
        self,
        offset: int,
        limit: int,
    ) -> tuple[list[EntityT], int]:
        """Return a page of entities and the total count.

        Args:
            offset: Number of records to skip (0-indexed).
            limit: Maximum number of records to return.

        Returns:
            A tuple of ``(page_items, total_count)``.
        """
        ...

    async def save(self, entity: EntityT) -> EntityT:
        """Persist the entity (insert or update) and return the saved copy.

        The returned entity may differ from the input if the database
        sets fields (e.g., ``created_at``, auto-incremented IDs).

        Args:
            entity: The entity to persist.

        Returns:
            The persisted entity with all database-assigned fields populated.
        """
        ...

    async def delete(self, entity_id: UUID) -> None:
        """Remove the entity with the given UUID.

        No-op if the entity does not exist.

        Args:
            entity_id: The primary key of the entity to remove.
        """
        ...

    async def exists(self, entity_id: UUID) -> bool:
        """Return ``True`` if an entity with the given UUID exists.

        Args:
            entity_id: The primary key to check.

        Returns:
            ``True`` if found, ``False`` otherwise.
        """
        ...

    async def count(self) -> int:
        """Return the total number of entities in the store.

        Returns:
            Total entity count (non-negative integer).
        """
        ...
