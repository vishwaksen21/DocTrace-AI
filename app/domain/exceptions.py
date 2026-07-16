"""Domain exception hierarchy.

All business-rule violations are represented as typed exceptions that
inherit from ``DomainError``.  This allows the API layer to catch them
with a single handler and map them to the correct HTTP status code.

Exception taxonomy::

    DomainError                            Base class (never raised directly)
    ├── NotFoundError                      Resource does not exist
    │   ├── DocumentNotFoundError
    │   ├── VersionNotFoundError
    │   ├── NodeNotFoundError
    │   ├── SelectionNotFoundError
    │   └── GenerationNotFoundError
    ├── ConflictError                      State conflict (e.g., duplicate)
    │   └── DuplicateVersionError
    ├── ValidationError                    Business-rule violation
    │   ├── EmptySelectionError            Selection contains no nodes
    │   ├── CrossVersionSelectionError     Nodes span multiple versions
    │   └── VersionNotReadyError           Version still processing
    └── ProcessingError                    Parsing / generation failure
        ├── PDFParsingError
        └── VersionDiffError

HTTP mapping (applied in ``app/api/errors.py`` in M11):
    NotFoundError         → 404 Not Found
    ConflictError         → 409 Conflict
    ValidationError       → 422 Unprocessable Entity
    ProcessingError       → 500 Internal Server Error (with user-facing message)
"""

from __future__ import annotations

from uuid import UUID

# ── Base ──────────────────────────────────────────────────────────────────────


class DomainError(Exception):
    """Base class for all domain-level errors.

    Carries a human-readable ``message`` and an optional ``details`` dict
    for structured context (e.g., ``{"document_id": "..."}``).

    Args:
        message: User-facing error description.
        details: Optional structured context for logging and API responses.
    """

    def __init__(
        self,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ── Not Found ─────────────────────────────────────────────────────────────────


class NotFoundError(DomainError):
    """A requested resource does not exist."""


class DocumentNotFoundError(NotFoundError):
    """No document found with the given UUID."""

    def __init__(self, document_id: UUID) -> None:
        super().__init__(
            f"Document '{document_id}' not found.",
            details={"document_id": str(document_id)},
        )
        self.document_id = document_id


class VersionNotFoundError(NotFoundError):
    """No version found with the given UUID."""

    def __init__(self, version_id: UUID) -> None:
        super().__init__(
            f"Version '{version_id}' not found.",
            details={"version_id": str(version_id)},
        )
        self.version_id = version_id


class NodeNotFoundError(NotFoundError):
    """No node found with the given UUID."""

    def __init__(self, node_id: UUID) -> None:
        super().__init__(
            f"Node '{node_id}' not found.",
            details={"node_id": str(node_id)},
        )
        self.node_id = node_id


class SelectionNotFoundError(NotFoundError):
    """No selection found with the given UUID."""

    def __init__(self, selection_id: UUID) -> None:
        super().__init__(
            f"Selection '{selection_id}' not found.",
            details={"selection_id": str(selection_id)},
        )
        self.selection_id = selection_id


class GenerationNotFoundError(NotFoundError):
    """No generation result found with the given ID."""

    def __init__(self, generation_id: str) -> None:
        super().__init__(
            f"Generation result '{generation_id}' not found.",
            details={"generation_id": generation_id},
        )
        self.generation_id = generation_id


# ── Conflict ──────────────────────────────────────────────────────────────────


class ConflictError(DomainError):
    """A state conflict prevents the requested operation."""


class DuplicateVersionError(ConflictError):
    """A version with this number already exists for the document.

    This should only be raised if the atomic ``get_next_version_number``
    guard in the repository fails — typically a concurrency bug.
    """

    def __init__(self, document_id: UUID, version_number: int) -> None:
        super().__init__(
            f"Version {version_number} already exists for document '{document_id}'.",
            details={
                "document_id": str(document_id),
                "version_number": version_number,
            },
        )
        self.document_id = document_id
        self.version_number = version_number


# ── Validation (business-rule violations) ─────────────────────────────────────


class BusinessValidationError(DomainError):
    """A business rule was violated.

    Named ``BusinessValidationError`` (not ``ValidationError``) to avoid
    shadowing ``pydantic.ValidationError`` which has a completely different
    meaning and calling convention.
    """


class EmptySelectionError(BusinessValidationError):
    """A selection was created or submitted with zero nodes.

    A meaningful QA generation requires at least one node.  The API layer
    should reject empty selections at the input-validation stage (Pydantic),
    but this exception guards the service layer as a second line of defence.
    """

    def __init__(self) -> None:
        super().__init__(
            "A selection must contain at least one node.  "
            "Provide one or more node IDs in the request body."
        )


class CrossVersionSelectionError(BusinessValidationError):
    """A selection references nodes from more than one document version.

    All nodes in a selection must belong to the same version so that the
    generated test cases have a coherent context.

    Args:
        version_ids: The set of distinct version UUIDs found in the selection.
    """

    def __init__(self, version_ids: set[UUID]) -> None:
        super().__init__(
            f"All selected nodes must belong to the same version.  "
            f"Found nodes from {len(version_ids)} different versions.",
            details={"version_ids": [str(v) for v in version_ids]},
        )
        self.version_ids = version_ids


class VersionNotReadyError(BusinessValidationError):
    """An operation requires a version in READY status, but it is not ready.

    Raised when a client attempts to create a selection or trigger a diff
    against a version that is still being processed (PROCESSING) or has
    failed (FAILED).

    Args:
        version_id: The version that is not yet ready.
        current_status: The actual current status of the version.
    """

    def __init__(self, version_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Version '{version_id}' is not ready (current status: '{current_status}').  "
            "Wait for parsing to complete before accessing nodes.",
            details={
                "version_id": str(version_id),
                "current_status": current_status,
            },
        )
        self.version_id = version_id
        self.current_status = current_status


# ── Processing Errors ─────────────────────────────────────────────────────────


class ProcessingError(DomainError):
    """A background processing step failed.

    Unlike the above exceptions (which represent invalid client input or
    state conflicts), ``ProcessingError`` indicates an internal failure in
    PDF parsing or version diffing.  The HTTP layer maps it to 500.
    """


class PDFParsingError(ProcessingError):
    """PDF parsing failed with an unrecoverable error.

    Args:
        filename: The name of the PDF file that failed.
        reason: A brief technical description of the failure.
    """

    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(
            f"Failed to parse PDF '{filename}': {reason}",
            details={"filename": filename, "reason": reason},
        )
        self.filename = filename
        self.reason = reason


class VersionDiffError(ProcessingError):
    """Version diff computation failed.

    Args:
        version_id_a: The base version UUID.
        version_id_b: The comparison version UUID.
        reason: A brief technical description of the failure.
    """

    def __init__(
        self,
        version_id_a: UUID,
        version_id_b: UUID,
        reason: str,
    ) -> None:
        super().__init__(
            f"Failed to diff version '{version_id_a}' against '{version_id_b}': {reason}",
            details={
                "version_id_a": str(version_id_a),
                "version_id_b": str(version_id_b),
                "reason": reason,
            },
        )
        self.version_id_a = version_id_a
        self.version_id_b = version_id_b
        self.reason = reason
