"""LLM response parsing and validation using Pydantic."""

from __future__ import annotations

import json
from uuid import UUID

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.entities import QATestCase


class LLMQATestCase(BaseModel):
    """Pydantic model representing a single QA test case from LLM output."""

    id: str = Field(..., description="Unique test case identifier (e.g. tc-001)")
    title: str = Field(..., description="Action-oriented title")
    objective: str = Field(..., description="Detailed objective of the test")
    preconditions: list[str] = Field(default_factory=list, description="Required system states")
    steps: list[str] = Field(..., description="Action steps to execute")
    expected_result: str = Field(..., description="Expected verified outcome")
    node_refs: list[str] = Field(
        default_factory=list, description="UUID references to source nodes"
    )

    @field_validator("preconditions", "steps", "node_refs", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[Any]:
        """Coerce single string values into single-element lists if returned by LLM."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()]
        return v


class LLMQAOutput(BaseModel):
    """Pydantic model representing the expected structural envelope."""

    test_cases: list[LLMQATestCase]


def validate_llm_json(content: str) -> tuple[list[QATestCase], list[str]]:
    """Parse and validate LLM completion JSON content.

    Processes JSON, extracts conforming QATestCases, and gathers validation
    errors.  Allows a mix of valid and invalid test cases (resulting in a
    PARTIAL generation status).

    Args:
        content: Raw JSON string returned from the LLM provider.

    Returns:
        A tuple of:
            - list[QATestCase]: Successfully validated test cases.
            - list[str]: Human-readable descriptions of validation failures.
    """
    errors: list[str] = []
    valid_cases: list[QATestCase] = []

    # Clean code blocks markup if model returned it (e.g. ```json ... ```)
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # Strip block markers
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return [], [f"Failed to decode JSON: {exc}"]

    if not isinstance(data, dict) or "test_cases" not in data:
        return [], ["Root element is not a dict containing 'test_cases'."]

    raw_cases = data.get("test_cases", [])
    if not isinstance(raw_cases, list):
        return [], ["'test_cases' is not a list."]

    for idx, raw_case in enumerate(raw_cases):
        try:
            validated = LLMQATestCase.model_validate(raw_case)

            # Map node_refs strings to UUID instances safely
            uuid_refs = []
            for r in validated.node_refs:
                try:
                    uuid_refs.append(UUID(r))
                except (ValueError, TypeError):
                    errors.append(f"Test case index {idx}: Invalid node UUID reference '{r}'")

            valid_cases.append(
                QATestCase(
                    id=validated.id,
                    title=validated.title,
                    objective=validated.objective,
                    preconditions=tuple(validated.preconditions),
                    steps=tuple(validated.steps),
                    expected_result=validated.expected_result,
                    node_refs=tuple(uuid_refs),
                )
            )
        except Exception as exc:
            errors.append(f"Test case index {idx} failed validation: {exc}")

    return valid_cases, errors
