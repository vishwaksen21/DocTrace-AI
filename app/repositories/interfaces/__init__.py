"""Repository interface contracts.

Exposes Protocols for loose coupling and easy mocking.
"""

from __future__ import annotations

from app.repositories.interfaces.document import DocumentRepositoryProtocol
from app.repositories.interfaces.node import NodeRepositoryProtocol
from app.repositories.interfaces.selection import (
    GenerationRepositoryProtocol,
    SelectionRepositoryProtocol,
)
from app.repositories.interfaces.version import VersionRepositoryProtocol

__all__ = [
    "DocumentRepositoryProtocol",
    "GenerationRepositoryProtocol",
    "NodeRepositoryProtocol",
    "SelectionRepositoryProtocol",
    "VersionRepositoryProtocol",
]
