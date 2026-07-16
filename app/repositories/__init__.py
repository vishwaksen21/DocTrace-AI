"""Repository layer package.

Contains:
    interfaces/    Protocol-based contracts each repository must satisfy
    document.py    SQLAlchemy implementation of DocumentRepository
    version.py     SQLAlchemy implementation of VersionRepository
    node.py        SQLAlchemy implementation of NodeRepository
    selection.py   SQLAlchemy implementation of SelectionRepository
    generation.py  MongoDB implementation of GenerationRepository

Design rationale
----------------
Repositories follow the Repository Pattern: they are the single gateway
between the domain/service layer and the persistence layer.  No SQL or
MongoDB query code appears outside this package.

Each repository implementation depends *only* on its interface Protocol,
not on a concrete class.  This makes services testable with simple
in-memory stubs and allows swapping persistence backends without changing
any business logic.
"""

from __future__ import annotations

from app.repositories.document import SqlAlchemyDocumentRepository
from app.repositories.generation import MongoGenerationRepository
from app.repositories.node import SqlAlchemyNodeRepository
from app.repositories.selection import SqlAlchemySelectionRepository
from app.repositories.version import SqlAlchemyVersionRepository

__all__ = [
    "MongoGenerationRepository",
    "SqlAlchemyDocumentRepository",
    "SqlAlchemyNodeRepository",
    "SqlAlchemySelectionRepository",
    "SqlAlchemyVersionRepository",
]
