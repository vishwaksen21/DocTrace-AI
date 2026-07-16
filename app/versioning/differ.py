"""Version diff orchestrator.

Produces a ``list[NodeDiff]`` from two ordered lists of ``Node`` entities,
representing what changed between an old and a new document version.

Public function
---------------
``diff_versions(old_nodes, new_nodes, tolerance)`` is the single entry
point.  All callers should import from ``app.versioning`` (the package)
rather than directly from this module.

Algorithm walkthrough
---------------------
Given::

    old_nodes = [A, B, C, D]   # nodes in old version
    new_nodes = [A', B, E, D]  # nodes in new version
    # A' = same position as A but different content (MODIFIED)
    # B  = unchanged at same position (UNCHANGED)
    # E  = new node, no match in old (ADDED)
    # D  = same content as old D but at a different position (MOVED)
    # C  = exists in old, no match in new (DELETED)

Phase 1 - Hash matching:
    new B  → matched to old B  at distance 0  → UNCHANGED,  B consumed
    new D  → matched to old D  at distance 1  → MOVED,       D consumed
    new A' → content hash differs → no hash match
    new E  → content hash differs → no hash match

Phase 2 - Position matching for unmatched new nodes:
    Unmatched new: [A' (pos 0), E (pos 2)]
    Unmatched old: [A (pos 0), C (pos 2)]
    A' (pos 0) ↔ A (pos 0)  → same position  → MODIFIED
    E  (pos 2) ↔ C (pos 2)  → same position  → could be MODIFIED
                              But E is brand new  → ADDED (no positional anchor)

    Position matching is positional anchor detection:
    If an unmatched new node is at position P and there is an unmatched
    old node at position P, the new node is MODIFIED (content at that
    position changed).  Otherwise it is ADDED.

Phase 3 - Residual classification:
    All remaining unmatched old nodes → DELETED.

Edge cases:
    - Empty old version (first upload): all new nodes are ADDED.
    - Empty new version (full deletion): all old nodes are DELETED.
    - Identical versions (re-upload): all nodes are UNCHANGED.
    - ``tolerance=0``: only exact position + hash matches are UNCHANGED;
      any position shift → MOVED treated as UNCHANGED content-wise.

Performance:
    O(n log n) dominated by sorting.  The inner loop over candidates is
    bounded by ``2 * tolerance + 1`` unconsumed nodes per hash bucket.
"""

from __future__ import annotations

from app.core.constants import DIFF_POSITION_TOLERANCE
from app.domain.entities import Node, NodeDiff
from app.domain.enums import DiffStatus
from app.versioning.matcher import HashPositionIndex


def diff_versions(
    old_nodes: list[Node],
    new_nodes: list[Node],
    tolerance: int = DIFF_POSITION_TOLERANCE,
) -> list[NodeDiff]:
    """Compute the structural diff between two document version node lists.

    The result covers every node in both versions:
    - Every new-version node appears in the output as ADDED, MODIFIED,
      UNCHANGED, or MOVED.
    - Every old-version node that was not matched appears as DELETED.

    The output list is sorted by ``new_position_index`` (ascending) for
    new-version nodes, followed by DELETED nodes sorted by their
    ``old_position_index``.  This ordering matches what the API layer
    expects for rendering the diff in document reading order.

    Args:
        old_nodes:  All nodes from the previous document version,
                    ordered by ``position_index``.
        new_nodes:  All nodes from the new document version,
                    ordered by ``position_index``.
        tolerance:  Position-distance tolerance for hash matching.
                    Defaults to ``DIFF_POSITION_TOLERANCE`` (3).
                    Set to 0 to require exact position + hash match.

    Returns:
        A list of ``NodeDiff`` objects describing every change.

    Raises:
        ValueError: If any node in ``old_nodes`` or ``new_nodes`` has a
                    duplicate ``position_index`` (indicates a corrupt version).
    """
    _validate_unique_positions(old_nodes, label="old_nodes")
    _validate_unique_positions(new_nodes, label="new_nodes")

    # ── Phase 1: Hash matching with position tolerance ─────────────────────
    index = HashPositionIndex(old_nodes)
    diffs: list[NodeDiff] = []
    unmatched_new: list[Node] = []

    for new_node in new_nodes:
        match = index.find_best_match(new_node, tolerance=tolerance)
        if match is not None:
            old_node, status = match
            index.consume(old_node)
            diffs.append(
                NodeDiff(
                    node=new_node,
                    status=status,
                    old_position_index=old_node.position_index,
                    new_position_index=new_node.position_index,
                )
            )
        else:
            unmatched_new.append(new_node)

    # ── Phase 2: Position-based matching for unmatched new nodes ───────────
    unmatched_old = index.unconsumed()
    old_by_position: dict[int, Node] = {n.position_index: n for n in unmatched_old}
    consumed_old_positions: set[int] = set()

    for new_node in unmatched_new:
        old_at_same_pos = old_by_position.get(new_node.position_index)
        if (
            old_at_same_pos is not None
            and old_at_same_pos.position_index not in consumed_old_positions
        ):
            # Same position, different content → MODIFIED
            consumed_old_positions.add(old_at_same_pos.position_index)
            diffs.append(
                NodeDiff(
                    node=new_node,
                    status=DiffStatus.MODIFIED,
                    old_position_index=old_at_same_pos.position_index,
                    new_position_index=new_node.position_index,
                )
            )
        else:
            # No positional anchor → ADDED
            diffs.append(
                NodeDiff(
                    node=new_node,
                    status=DiffStatus.ADDED,
                    old_position_index=None,
                    new_position_index=new_node.position_index,
                )
            )

    # ── Phase 3: Remaining old nodes → DELETED ─────────────────────────────
    for old_node in unmatched_old:
        if old_node.position_index not in consumed_old_positions:
            diffs.append(
                NodeDiff(
                    node=old_node,
                    status=DiffStatus.DELETED,
                    old_position_index=old_node.position_index,
                    new_position_index=None,
                )
            )

    # Sort: new-version nodes by new_position_index; DELETED by old_position_index
    diffs.sort(key=_sort_key)
    return diffs


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sort_key(diff: NodeDiff) -> tuple[int, int]:
    """Produce a stable sort key for a NodeDiff.

    DELETED nodes have ``new_position_index = None``.  They sort after all
    non-deleted nodes (primary key = 1) to keep the diff list in reading
    order for non-deleted content followed by all deletions.

    Returns:
        (is_deleted: 0|1, position: int)
    """
    if diff.status == DiffStatus.DELETED:
        return (1, diff.old_position_index or 0)
    return (0, diff.new_position_index or 0)


def _validate_unique_positions(nodes: list[Node], label: str) -> None:
    """Raise ValueError if any two nodes share a ``position_index``.

    Args:
        nodes: The node list to validate.
        label: Human-readable name for the list (used in the error message).

    Raises:
        ValueError: On the first duplicate position found.
    """
    seen: set[int] = set()
    for node in nodes:
        if node.position_index in seen:
            raise ValueError(
                f"Duplicate position_index {node.position_index} found in {label}. "
                "This indicates a corrupt or incorrectly assembled version."
            )
        seen.add(node.position_index)


def summarise_diff(diffs: list[NodeDiff]) -> dict[str, int]:
    """Return a count of nodes per DiffStatus in the diff result.

    Useful for logging and the version diff API response summary.

    Args:
        diffs: Output of ``diff_versions()``.

    Returns:
        Dict with keys ``"unchanged"``, ``"modified"``, ``"added"``,
        ``"deleted"``, ``"moved"``; values are counts.

    Example::

        counts = summarise_diff(diffs)
        # {"unchanged": 42, "modified": 3, "added": 1, "deleted": 0, "moved": 0}
    """
    counts: dict[str, int] = {
        "unchanged": 0,
        "modified": 0,
        "added": 0,
        "deleted": 0,
        "moved": 0,
    }
    for diff in diffs:
        counts[str(diff.status)] += 1
    return counts
