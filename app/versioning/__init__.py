"""Document version comparison engine.

This package implements the position-anchored hash matching algorithm
that determines what changed between two versions of a parsed document.

Public API::

    from app.versioning import diff_versions

    diffs: list[NodeDiff] = diff_versions(old_nodes, new_nodes)

Design overview
---------------
The diff algorithm operates in three phases:

Phase 1 - Hash matching with position tolerance
    For every node in the new version, search for a matching ``content_hash``
    in the old version within a configurable position window (default ±3).
    Matched pairs are labelled ``UNCHANGED`` (same position) or ``MOVED``
    (same content, different position).

Phase 2 - Position-based matching for unmatched nodes
    Nodes that were not hash-matched are compared by position.  A new node
    whose position aligns with an unmatched old node is labelled ``MODIFIED``
    (content changed at the same structural location).

Phase 3 - Residual classification
    Remaining unmatched new nodes are ``ADDED``.
    Remaining unmatched old nodes are ``DELETED``.

The algorithm is O(n log n) in the number of nodes, dominated by the
sort of position candidates during Phase 1 lookup.

OCR / large documents note
    For documents with thousands of nodes the tolerance window keeps
    lookups efficient: each new node is compared against at most
    ``2 * DIFF_POSITION_TOLERANCE + 1`` candidates, not the entire old list.
"""

from __future__ import annotations

from app.versioning.differ import diff_versions

__all__ = ["diff_versions"]
