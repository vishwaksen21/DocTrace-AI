"""Generation schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import GenerationStatus


class QATestCaseResponse(BaseModel):
    """Response representing a single generated QA test case."""

    model_config = {"from_attributes": True}

    id: str
    title: str
    objective: str
    preconditions: list[str]
    steps: list[str]
    expected_result: str
    node_refs: list[UUID]


class GenerationResponse(BaseModel):
    """Response representing a QA generation result."""

    model_config = {"from_attributes": True}

    id: str = Field(description="MongoDB BSON ObjectId hex string identifier")
    selection_id: UUID
    document_id: UUID
    version_id: UUID
    model: str
    prompt_tokens: int
    completion_tokens: int
    status: GenerationStatus
    test_cases: list[QATestCaseResponse]
    validation_errors: list[str]
    created_at: datetime
    duration_ms: float
