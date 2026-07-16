"""Domain enumerations.

All controlled vocabularies used across the domain, persistence, and API
layers are centralised here.  Using ``enum.StrEnum`` (Python 3.11+) means
enum members serialize to their string value natively — no ``.value``
required and JSON serialization works out of the box with Pydantic and
the standard library ``json`` module.

Usage::

    from app.domain.enums import NodeType, VersionStatus, DiffStatus

    if node.node_type == NodeType.HEADING:
        ...

    if status == VersionStatus.READY:
        ...
"""

from __future__ import annotations

from enum import StrEnum, auto


class NodeType(StrEnum):
    """Structural type of a parsed document node.

    Variants:
        HEADING    A section heading (H1-H6). ``heading_level`` discriminates
                   the depth within the hierarchy.
        PARAGRAPH  A body text block — the default for unclassified text.
        TABLE      A structured tabular block stored in Markdown table format.
        LIST       A list container (ordered or unordered).
        LIST_ITEM  A single item within a LIST parent.

    Confidence note:
        If the parser cannot classify a block with confidence ≥ 0.8 (see
        ``HEADING_MIN_CONFIDENCE`` in ``app.core.constants``), it is stored
        as ``PARAGRAPH`` and the ambiguity is logged.  We never silently
        upgrade uncertain text to headings.
    """

    HEADING = auto()
    PARAGRAPH = auto()
    TABLE = auto()
    LIST = auto()
    LIST_ITEM = auto()


class VersionStatus(StrEnum):
    """Processing lifecycle status of a document version.

    Variants:
        PROCESSING  The version record exists but PDF parsing has not
                    completed.  This is the initial state immediately after
                    a ``202 Accepted`` response is returned to the client.
        READY       Parsing completed successfully.  Nodes are persisted
                    and the version is available for diff and selection.
        FAILED      Parsing encountered an unrecoverable error.  The raw
                    error message is stored for diagnostics.  A client may
                    retry by uploading the document again.
    """

    PROCESSING = auto()
    READY = auto()
    FAILED = auto()


class DiffStatus(StrEnum):
    """Change status of a node when compared across two document versions.

    Computed by the position-anchored hash matching algorithm in
    ``app.versioning.differ``.

    Variants:
        UNCHANGED  Same ``content_hash`` found at the same position (±tolerance).
        MODIFIED   ``content_hash`` differs; the node at this position changed.
        ADDED      Node exists in the new version but not in the old version.
        DELETED    Node existed in the old version but is absent in the new version.
        MOVED      Same ``content_hash`` found but at a different position
                   (outside the tolerance window).  For QA purposes, treated
                   as UNCHANGED since the content itself did not change.

    The ordering above reflects the expected frequency in typical document updates:
    most nodes will be UNCHANGED, with a small fraction MODIFIED or ADDED.
    """

    UNCHANGED = auto()
    MODIFIED = auto()
    ADDED = auto()
    DELETED = auto()
    MOVED = auto()


class GenerationStatus(StrEnum):
    """Processing status of an LLM generation job.

    Variants:
        PROCESSING  The generation request has been accepted and handed off
                    to a ``BackgroundTask``.  This is the state immediately
                    after a ``202 Accepted`` response.
        SUCCESS     The LLM responded with valid, schema-conforming output.
                    Test cases are available in the result document.
        PARTIAL     The LLM returned a response, but some test cases failed
                    Pydantic validation.  Valid cases are stored; the
                    validation errors are recorded alongside them.
        FAILED      The LLM call failed after all retries (timeout, 5xx,
                    or rate limit exhaustion).  No test cases were produced.
    """

    PROCESSING = auto()
    SUCCESS = auto()
    PARTIAL = auto()
    FAILED = auto()
