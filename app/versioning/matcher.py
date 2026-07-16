"""Position-anchored hash matcher for document version comparison.

This module implements the low-level matching primitives used by the
diff engine.  It is deliberately separated from ``differ.py`` so that
the matching strategy can be swapped (e.g., to LCS-based matching for
future research) without changing the diff orchestration logic.

Algorithm: Position-Anchored Hash Matching
------------------------------------------
Given a pool of old nodes indexed by ``content_hash``, and a new node
at position ``P`` with hash ``H``:

1. Retrieve all old nodes with the same ``content_hash`` = H.
2. Among those candidates, prefer the one whose ``position_index``
   is closest to P.
3. If the closest candidate's distance is <= ``tolerance``, it is a match.
   The match is classified as:
   - ``UNCHANGED`` if ``abs(old_pos - P) == 0``
   - ``MOVED``     if ``0 < abs(old_pos - P) <= tolerance``
4. If no candidate is within tolerance → no match (new node is unmatched).

Why position-anchored?
    Pure hash matching (without positional awareness) would mark a
    reordered section as "UNCHANGED" even when its surrounding context
    changed.  Position tolerance threads the needle: robust to minor
    reordering (swapped adjacent paragraphs) while correctly detecting
    structural rearrangements.

Failure modes (documented in the implementation plan):
    - Two nodes with identical content that swapped positions → both
      appear UNCHANGED.  Acceptable: content is identical.
    - Heading level change with no content change → hash changes →
      correctly flagged as MODIFIED.
    - Table cell reordering with identical semantic content → hash
      changes → correctly flagged as MODIFIED.
"""

from __future__ import annotations

from collections import defaultdict

from app.core.constants import DIFF_POSITION_TOLERANCE
from app.domain.entities import Node
from app.domain.enums import DiffStatus


class HashPositionIndex:
    """An index of old-version nodes keyed by ``content_hash``.

    Enables O(1) lookup of candidate nodes by hash, followed by an
    O(k) scan across at most ``2 * tolerance + 1`` position candidates
    where k is bounded by the number of nodes with an identical hash
    (expected to be very small for non-repeated content).

    Usage::

        index = HashPositionIndex(old_nodes)
        match = index.find_best_match(new_node, tolerance=3)
        if match:
            matched_node, diff_status = match
            index.consume(matched_node)   # remove from available pool
    """

    def __init__(self, nodes: list[Node]) -> None:
        """Build the index from a list of old-version nodes.

        Args:
            nodes: All nodes from the old document version, in any order.
        """
        # hash -> list of nodes with that hash, sorted by position_index
        self._by_hash: dict[str, list[Node]] = defaultdict(list)
        for node in nodes:
            self._by_hash[node.content_hash].append(node)
        # Sort each bucket by position for deterministic closest-match selection
        for bucket in self._by_hash.values():
            bucket.sort(key=lambda n: n.position_index)

        # Track which nodes have already been consumed (matched)
        self._consumed: set[int] = set()  # stores node.position_index

    def find_best_match(
        self,
        new_node: Node,
        tolerance: int = DIFF_POSITION_TOLERANCE,
    ) -> tuple[Node, DiffStatus] | None:
        """Find the best matching old-version node for ``new_node``.

        Searches by ``content_hash`` first, then selects the unconsumed
        candidate whose ``position_index`` is closest to the new node's
        ``position_index``.

        Args:
            new_node:  The new-version node to match.
            tolerance: Maximum allowed position distance for a match.
                       Defaults to ``DIFF_POSITION_TOLERANCE`` (3).

        Returns:
            A ``(matched_node, DiffStatus)`` tuple if a match is found
            within ``tolerance``, or ``None`` if no match exists.

            The status is:
                - ``DiffStatus.UNCHANGED`` if the matched node is at the
                  same position (distance == 0).
                - ``DiffStatus.MOVED``     if the distance is 1..tolerance.
        """
        candidates = self._by_hash.get(new_node.content_hash, [])
        best: Node | None = None
        best_distance = tolerance + 1  # start above threshold

        for candidate in candidates:
            if candidate.position_index in self._consumed:
                continue
            distance = abs(candidate.position_index - new_node.position_index)
            if distance < best_distance:
                best = candidate
                best_distance = distance

        if best is None:
            return None

        status = DiffStatus.UNCHANGED if best_distance == 0 else DiffStatus.MOVED
        return best, status

    def consume(self, node: Node) -> None:
        """Mark a node as consumed so it cannot be matched again.

        Must be called immediately after a successful ``find_best_match``
        to prevent the same old node from matching multiple new nodes.

        Args:
            node: The matched old-version node to remove from the pool.
        """
        self._consumed.add(node.position_index)

    def unconsumed(self) -> list[Node]:
        """Return all old-version nodes that were never matched.

        These are candidates for ``DELETED`` classification.

        Returns:
            List of unmatched old nodes, sorted by ``position_index``.
        """
        result: list[Node] = []
        for bucket in self._by_hash.values():
            for node in bucket:
                if node.position_index not in self._consumed:
                    result.append(node)
        result.sort(key=lambda n: n.position_index)
        return result
