"""Service layer package.

Orchestrates all business logic use cases and encapsulates validation rules.
"""

from __future__ import annotations

from app.services.document import DocumentService
from app.services.generation import GenerationService, generate_qa_cases_task
from app.services.selection import SelectionService
from app.services.version import VersionService, parse_and_persist_version_task

__all__ = [
    "DocumentService",
    "GenerationService",
    "SelectionService",
    "VersionService",
    "generate_qa_cases_task",
    "parse_and_persist_version_task",
]
