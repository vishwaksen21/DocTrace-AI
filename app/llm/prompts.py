"""LLM prompt templates for QA test-case generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities import Node

SYSTEM_PROMPT = """You are an elite QA Automation Engineer and Software Auditor.
Your task is to analyze document sections (requirements, specifications, procedures)
and generate high-quality, structured QA test cases.

For the user-provided list of document nodes, generate test cases conforming to the JSON schema.

Each test case MUST contain:
- id: A unique test identifier (e.g., "tc-001").
- title: A concise, action-oriented title.
- objective: What is being verified.
- preconditions: What system state is required before execution.
- steps: Detailed, step-by-step action instructions.
- expected_result: The verified outcome or assertion.
- node_refs: A list of UUID string references to the specific document nodes this test case covers.

Make the test cases realistic, exhaustive, and directly mapped to the source document requirements.
Only return a JSON object containing the "test_cases" array. Do not output markdown code blocks
or any conversational text around the JSON.
"""


def build_user_prompt(nodes: list[Node]) -> str:
    """Build a prompt containing the text and UUID references of the selected nodes.

    Args:
        nodes: Sorted list of Node domain entities selected by the user.

    Returns:
        Formatted prompt text for the LLM client.
    """
    lines = [
        "Please analyze the following document fragments and generate conforming QA test cases:\n"
    ]
    for node in nodes:
        # Include node type, heading level if present, UUID, and content for full context
        type_str: str = node.node_type.value
        if node.heading_level:
            type_str = f"{type_str} H{node.heading_level}"

        lines.append(f"--- Node {node.id} ({type_str}) ---")
        lines.append(node.content.strip())
        lines.append("")

    return "\n".join(lines)
