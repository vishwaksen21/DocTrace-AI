"""Domain entity dataclasses.

Domain entities represent the core business objects of DocTrace AI.
They are pure Python frozen dataclasses — no SQLAlchemy, no Pydantic,
no FastAPI imports.

Entity vs. ORM Model distinction
---------------------------------
- **Entities** (this file): Immutable value objects used by the service
  layer and domain logic.  Constructed from ORM models in repositories.
- **ORM Models** (``app/models/``): SQLAlchemy mapped classes.  Used only
  within the repository layer to talk to the database.

This separation ensures the service layer is testable without a database:
you can pass plain entity instances to service methods without an ORM session.

Immutability
-------------
All entities use ``frozen=True`` and ``slots=True``.  To "modify" an entity,
create a new one with ``dataclasses.replace(entity, field=new_value)``.
This enforces functional-style domain logic and prevents accidental mutation.

IDs
----
All entities use UUID4 primary keys.  The service layer is responsible for
generating IDs *before* persisting (using ``uuid.uuid4()``), which decouples
entity creation from database round-trips and makes testing trivially simple.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.enums import (
    DiffStatus,
    GenerationStatus,
    NodeType,
    VersionStatus,
)

# ── Document ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Document:
    """Top-level aggregate representing a tracked document.

    A document persists across multiple uploads (versions).  Its identity
    is stable; only its versions change.

    Attributes:
        id: Unique identifier (UUID4).
        title: Human-readable document title.  Derived from the filename
            on first upload; can be updated via a PATCH endpoint (M11).
        original_filename: The filename of the first uploaded PDF, preserved
            for auditability.
        created_at: Timestamp of the first upload.
        updated_at: Timestamp of the most recent metadata change.
    """

    id: UUID
    title: str
    original_filename: str
    created_at: datetime
    updated_at: datetime


# ── Version ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Version:
    """A single uploaded revision of a document.

    Versions are append-only: once created, they are never modified
    (except for a ``status`` update from ``PROCESSING`` to ``READY``
    or ``FAILED`` after background parsing completes).

    Attributes:
        id: Unique identifier (UUID4).
        document_id: Parent document's UUID.
        version_number: Monotonically increasing integer per document,
            starting at 1.  Unique per ``(document_id, version_number)``.
        upload_filename: The PDF filename for this specific upload.
            May differ from ``Document.original_filename`` if the user
            renamed the file between uploads.
        status: Current parse lifecycle status (see ``VersionStatus``).
        error_message: Non-None only when ``status == VersionStatus.FAILED``.
            Contains a brief technical description of the parse failure.
        created_at: Timestamp of the upload event (``202 Accepted`` response).
    """

    id: UUID
    document_id: UUID
    version_number: int
    upload_filename: str
    status: VersionStatus
    created_at: datetime
    error_message: str | None = None

    @property
    def is_ready(self) -> bool:
        """Return True when this version's nodes are available for querying."""
        return self.status == VersionStatus.READY

    @property
    def is_processing(self) -> bool:
        """Return True when background parsing is still in progress."""
        return self.status == VersionStatus.PROCESSING


# ── Node ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Node:
    """A single structural unit extracted from a PDF version.

    Nodes form a tree: heading nodes are parents of the paragraph and
    list nodes that fall under them.  Root-level nodes have no parent.

    Attributes:
        id: Unique identifier (UUID4).
        version_id: The version this node belongs to.
        parent_id: UUID of the parent heading node, or ``None`` if this
            is a root-level node.
        node_type: Structural type (heading, paragraph, table, list, list_item).
        heading_level: 1-6 for ``HEADING`` nodes; ``None`` for all others.
        content: The raw text content of the node.  Tables are stored in
            Markdown table format (``| col1 | col2 |...``).
        content_hash: SHA-256 hex digest of the normalised content.
            Used for O(1) change detection across versions.
        position_index: Global 0-based ordering within the version.
            Preserved across re-uploads to disambiguate duplicate content.
        path: Materialized path string (e.g. ``"0"``, ``"0.2"``, ``"0.2.1"``)
            for efficient ancestor/descendant queries without recursion.
        created_at: Timestamp of node creation (set once at parse time).
    """

    id: UUID
    version_id: UUID
    node_type: NodeType
    content: str
    content_hash: str
    position_index: int
    path: str
    created_at: datetime
    parent_id: UUID | None = None
    heading_level: int | None = None

    def __post_init__(self) -> None:
        """Validate heading-level consistency at construction time."""
        # Use object.__setattr__ because the dataclass is frozen
        if self.node_type == NodeType.HEADING and self.heading_level is None:
            raise ValueError(
                "heading_level must be set for HEADING nodes.  "
                f"Node at position {self.position_index} has node_type=HEADING "
                "but heading_level=None."
            )
        if self.node_type != NodeType.HEADING and self.heading_level is not None:
            raise ValueError(
                "heading_level must be None for non-HEADING nodes.  "
                f"Node at position {self.position_index} has "
                f"node_type={self.node_type} but heading_level={self.heading_level}."
            )
        if self.heading_level is not None and not (1 <= self.heading_level <= 6):
            raise ValueError(f"heading_level must be 1-6; got {self.heading_level}.")
        if len(self.content_hash) != 64:
            raise ValueError(
                f"content_hash must be a 64-character SHA-256 hex digest; "
                f"got length {len(self.content_hash)}."
            )


# ── Diff Node Result ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NodeDiff:
    """The diff result for a single node comparison across two versions.

    Produced by the versioning diff engine (``app.versioning.differ``).

    Attributes:
        node: The node from the *new* version.  For DELETED nodes, this
            is the node from the *old* version.
        status: The change classification (see ``DiffStatus``).
        old_position_index: The position of the matching node in the old
            version, or ``None`` for ADDED nodes.
        new_position_index: The position in the new version, or ``None``
            for DELETED nodes.
    """

    node: Node
    status: DiffStatus
    old_position_index: int | None = None
    new_position_index: int | None = None


# ── Selection ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Selection:
    """A named set of nodes chosen for QA test-case generation.

    A selection captures which nodes the user wants to generate test cases
    for.  All nodes must belong to the same version.

    Attributes:
        id: Unique identifier (UUID4).
        version_id: The version all selected nodes belong to.
        node_ids: The ordered list of selected node UUIDs.  Order is
            preserved from the client request so the LLM receives nodes
            in document reading order.
        name: Optional user-provided label (e.g. ``"Section 3 - Requirements"``).
        created_at: Timestamp of selection creation.
    """

    id: UUID
    version_id: UUID
    node_ids: tuple[UUID, ...]
    created_at: datetime
    name: str | None = None

    def __post_init__(self) -> None:
        """Reject empty selections at construction time."""
        if not self.node_ids:
            raise ValueError(
                "A Selection must contain at least one node.  Provide one or more node_ids."
            )


# ── Generation Result ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class QATestCase:
    """A single QA test case generated by the LLM.

    Attributes:
        id: Client-facing identifier (e.g., ``"tc-001"``).  Assigned by
            the LLM in the response; uniqueness is not enforced by the database.
        title: Short title of the test case.
        objective: What behaviour is being tested.
        preconditions: List of precondition statements.
        steps: Ordered list of test steps.
        expected_result: The expected outcome of the test.
        node_refs: UUIDs of the nodes that this test case references.
            A single test case may reference multiple source nodes.
    """

    id: str
    title: str
    objective: str
    preconditions: tuple[str, ...]
    steps: tuple[str, ...]
    expected_result: str
    node_refs: tuple[UUID, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """The complete result of an LLM QA generation job.

    Stored in MongoDB (``generation_results`` collection) because the
    structure is schema-flexible and the raw response is valuable for
    debugging and re-processing.

    Attributes:
        id: MongoDB ObjectId string.  ``None`` before the first save.
        selection_id: The selection that triggered this generation.
        document_id: Denormalised for efficient queries without a join.
        version_id: Denormalised for efficient queries without a join.
        model: The exact model identifier returned by the LLM provider.
        prompt_tokens: Input token count.
        completion_tokens: Output token count.
        status: Generation lifecycle status (see ``GenerationStatus``).
        raw_response: The full LLM API response payload.
        test_cases: Successfully parsed and validated test cases.
        validation_errors: Descriptions of test cases that failed validation.
        created_at: Timestamp of the generation request.
        duration_ms: Total LLM round-trip time in milliseconds.
    """

    selection_id: UUID
    document_id: UUID
    version_id: UUID
    model: str
    prompt_tokens: int
    completion_tokens: int
    status: GenerationStatus
    raw_response: str
    test_cases: tuple[QATestCase, ...]
    validation_errors: tuple[str, ...]
    created_at: datetime
    duration_ms: float
    id: str | None = None

    @property
    def total_tokens(self) -> int:
        """Sum of prompt and completion token counts."""
        return self.prompt_tokens + self.completion_tokens

    def to_mongo_doc(self) -> dict[str, Any]:
        """Serialize to a MongoDB-compatible dictionary.

        Converts UUID fields to strings and tuples to lists for BSON
        compatibility.  Called by the generation repository before
        inserting into the ``generation_results`` collection.

        Returns:
            A dict suitable for passing to ``Motor.insert_one()``.
        """
        return {
            "selection_id": str(self.selection_id),
            "document_id": str(self.document_id),
            "version_id": str(self.version_id),
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "status": str(self.status),
            "raw_response": self.raw_response,
            "test_cases": [
                {
                    "id": tc.id,
                    "title": tc.title,
                    "objective": tc.objective,
                    "preconditions": list(tc.preconditions),
                    "steps": list(tc.steps),
                    "expected_result": tc.expected_result,
                    "node_refs": [str(r) for r in tc.node_refs],
                }
                for tc in self.test_cases
            ],
            "validation_errors": list(self.validation_errors),
            "created_at": self.created_at.isoformat(),
            "duration_ms": self.duration_ms,
        }
