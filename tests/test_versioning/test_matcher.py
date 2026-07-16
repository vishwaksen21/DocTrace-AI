"""Tests for app/versioning/matcher.py — HashPositionIndex."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.entities import Node
from app.domain.enums import DiffStatus, NodeType
from app.versioning.matcher import HashPositionIndex

# ── Fixtures / helpers ────────────────────────────────────────────────────────

_VERSION_ID = uuid4()
_NOW = datetime.now(tz=UTC)


def _node(
    position: int,
    content: str = "body text",
    node_type: NodeType = NodeType.PARAGRAPH,
    heading_level: int | None = None,
    content_hash: str | None = None,
    node_id: UUID | None = None,
) -> Node:
    """Create a minimal Node for testing."""
    if content_hash is None:
        # Deterministic fake hash based on content text
        content_hash = (content[:64]).ljust(64, "0")
    return Node(
        id=node_id or uuid4(),
        version_id=_VERSION_ID,
        node_type=node_type,
        content=content,
        content_hash=content_hash,
        position_index=position,
        path=str(position),
        created_at=_NOW,
        heading_level=heading_level,
    )


def _hash(s: str) -> str:
    """Produce a deterministic 64-char fake hash from a short seed string."""
    return s[:1].ljust(64, s[-1] if s else "0")


# ── HashPositionIndex.find_best_match ─────────────────────────────────────────


class TestFindBestMatch:
    def test_exact_position_match_returns_unchanged(self) -> None:
        h = _hash("A")
        old = [_node(0, "text_a", content_hash=h)]
        index = HashPositionIndex(old)
        new = _node(0, "text_a", content_hash=h)
        result = index.find_best_match(new, tolerance=3)
        assert result is not None
        matched_node, status = result
        assert status == DiffStatus.UNCHANGED
        assert matched_node.position_index == 0

    def test_within_tolerance_returns_moved(self) -> None:
        h = _hash("B")
        old = [_node(0, "text_b", content_hash=h)]
        index = HashPositionIndex(old)
        new = _node(2, "text_b", content_hash=h)  # distance=2, within tolerance=3
        result = index.find_best_match(new, tolerance=3)
        assert result is not None
        _, status = result
        assert status == DiffStatus.MOVED

    def test_exactly_at_tolerance_boundary_returns_moved(self) -> None:
        h = _hash("C")
        old = [_node(0, "text_c", content_hash=h)]
        index = HashPositionIndex(old)
        new = _node(3, "text_c", content_hash=h)  # distance=3 == tolerance
        result = index.find_best_match(new, tolerance=3)
        assert result is not None
        _, status = result
        assert status == DiffStatus.MOVED

    def test_beyond_tolerance_returns_none(self) -> None:
        h = _hash("D")
        old = [_node(0, "text_d", content_hash=h)]
        index = HashPositionIndex(old)
        new = _node(4, "text_d", content_hash=h)  # distance=4 > tolerance=3
        result = index.find_best_match(new, tolerance=3)
        assert result is None

    def test_no_hash_match_returns_none(self) -> None:
        old = [_node(0, "old text", content_hash=_hash("A"))]
        index = HashPositionIndex(old)
        new = _node(0, "new text", content_hash=_hash("B"))
        assert index.find_best_match(new, tolerance=3) is None

    def test_empty_index_returns_none(self) -> None:
        index = HashPositionIndex([])
        new = _node(0, "anything", content_hash=_hash("X"))
        assert index.find_best_match(new, tolerance=3) is None

    def test_chooses_closest_candidate_when_multiple_same_hash(self) -> None:
        h = _hash("E")
        old = [
            _node(0, "dup", content_hash=h),
            _node(5, "dup", content_hash=h),
        ]
        index = HashPositionIndex(old)
        new = _node(4, "dup", content_hash=h)  # closer to pos 5 than pos 0
        result = index.find_best_match(new, tolerance=3)
        assert result is not None
        matched, _ = result
        assert matched.position_index == 5

    def test_tolerance_zero_requires_exact_position(self) -> None:
        h = _hash("F")
        old = [_node(0, "exact", content_hash=h)]
        index = HashPositionIndex(old)
        new_exact = _node(0, "exact", content_hash=h)
        new_off = _node(1, "exact", content_hash=h)
        assert index.find_best_match(new_exact, tolerance=0) is not None
        assert index.find_best_match(new_off, tolerance=0) is None


# ── HashPositionIndex.consume ─────────────────────────────────────────────────


class TestConsume:
    def test_consumed_node_not_matched_again(self) -> None:
        h = _hash("G")
        old_node = _node(0, "text_g", content_hash=h)
        index = HashPositionIndex([old_node])

        new1 = _node(0, "text_g", content_hash=h)
        result1 = index.find_best_match(new1, tolerance=3)
        assert result1 is not None
        matched, _ = result1
        index.consume(matched)

        new2 = _node(1, "text_g", content_hash=h)
        result2 = index.find_best_match(new2, tolerance=3)
        assert result2 is None  # old node already consumed

    def test_multiple_same_hash_each_consumed_independently(self) -> None:
        h = _hash("H")
        old = [_node(0, "dup_h", content_hash=h), _node(1, "dup_h", content_hash=h)]
        index = HashPositionIndex(old)

        new1 = _node(0, "dup_h", content_hash=h)
        r1 = index.find_best_match(new1, tolerance=3)
        assert r1 is not None
        index.consume(r1[0])

        new2 = _node(1, "dup_h", content_hash=h)
        r2 = index.find_best_match(new2, tolerance=3)
        assert r2 is not None  # second node still available
        index.consume(r2[0])

        new3 = _node(2, "dup_h", content_hash=h)
        r3 = index.find_best_match(new3, tolerance=3)
        assert r3 is None  # all consumed


# ── HashPositionIndex.unconsumed ──────────────────────────────────────────────


class TestUnconsumed:
    def test_all_nodes_unconsumed_initially(self) -> None:
        old = [_node(i, f"node{i}", content_hash=_hash(str(i))) for i in range(5)]
        index = HashPositionIndex(old)
        unconsumed = index.unconsumed()
        assert len(unconsumed) == 5

    def test_consumed_nodes_excluded(self) -> None:
        h = _hash("I")
        old_node = _node(0, "text_i", content_hash=h)
        index = HashPositionIndex([old_node])
        new = _node(0, "text_i", content_hash=h)
        r = index.find_best_match(new, tolerance=3)
        assert r is not None
        index.consume(r[0])
        assert index.unconsumed() == []

    def test_unconsumed_sorted_by_position(self) -> None:
        old = [_node(i, f"n{i}", content_hash=_hash(str(i))) for i in [3, 1, 4, 1, 5]]
        # note: duplicate position 1 — the HashPositionIndex allows this for
        # the internal structure; _validate_unique_positions in differ catches it
        index = HashPositionIndex(old)
        unconsumed = index.unconsumed()
        positions = [n.position_index for n in unconsumed]
        assert positions == sorted(positions)
