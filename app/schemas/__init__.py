"""Schemas package exposing Pydantic request/response validation schemas."""

from __future__ import annotations

from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.document import DocumentCreate, DocumentResponse, DocumentUploadResponse
from app.schemas.generation import GenerationResponse, QATestCaseResponse
from app.schemas.node import NodeResponse
from app.schemas.selection import SelectionCreate, SelectionResponse, SelectionWithNodesResponse
from app.schemas.version import NodeDiffResponse, VersionResponse

__all__ = [
    "DocumentCreate",
    "DocumentResponse",
    "DocumentUploadResponse",
    "ErrorResponse",
    "GenerationResponse",
    "NodeDiffResponse",
    "NodeResponse",
    "PaginatedResponse",
    "QATestCaseResponse",
    "SelectionCreate",
    "SelectionResponse",
    "SelectionWithNodesResponse",
    "VersionResponse",
]

# Rebuild models with forward references now that all schemas are imported
DocumentUploadResponse.model_rebuild()
SelectionWithNodesResponse.model_rebuild()
