"""Tests for app/versioning/differ.py — diff_versions and summarise_diff."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities import Node
from app.domain.enums import DiffStatus, NodeType
from app.versioning.differ import diff_versions, summarise_diff

# ── Helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime.now(tz=UTC)
_V1 = uuid4()
_V2 = uuid4()


def _node(
    position: int,
    content_hash: str,
    version_id=_V1,
    node_type: NodeType = NodeType.PARAGRAPH,
    heading_level: int | None = None,
) -> Node:
    return Node(
        id=uuid4(),
        version_id=version_id,
        node_type=node_type,
        content=f"content_{content_hash[:4]}",
        content_hash=content_hash,
        position_index=position,
        path=str(position),
        created_at=_NOW,
        heading_level=heading_level,
    )


def _hash(seed: str) -> str:
    """Return a deterministic 64-char fake hash from a seed string."""
    return seed[:1].ljust(64, "a")


def _hashes(*seeds: str) -> list[str]:
    return [_hash(s) for s in seeds]


# ── Empty version cases ───────────────────────────────────────────────────────


class TestEmptyVersions:
    def test_both_empty_returns_empty(self) -> None:
        assert diff_versions([], []) == []

    def test_empty_old_all_added(self) -> None:
        new = [_node(i, _hash(str(i)), version_id=_V2) for i in range(3)]
        diffs = diff_versions([], new)
        assert len(diffs) == 3
        assert all(d.status == DiffStatus.ADDED for d in diffs)

    def test_empty_new_all_deleted(self) -> None:
        old = [_node(i, _hash(str(i)), version_id=_V1) for i in range(3)]
        diffs = diff_versions(old, [])
        assert len(diffs) == 3
        assert all(d.status == DiffStatus.DELETED for d in diffs)


# ── Identical versions ────────────────────────────────────────────────────────


class TestIdenticalVersions:
    def test_all_nodes_unchanged(self) -> None:
        h0, h1, h2 = _hashes("A", "B", "C")
        old = [_node(0, h0), _node(1, h1), _node(2, h2)]
        new = [
            _node(0, h0, version_id=_V2),
            _node(1, h1, version_id=_V2),
            _node(2, h2, version_id=_V2),
        ]
        diffs = diff_versions(old, new)
        assert all(d.status == DiffStatus.UNCHANGED for d in diffs)
        assert len(diffs) == 3

    def test_unchanged_nodes_have_correct_position_refs(self) -> None:
        h = _hash("X")
        old = [_node(5, h)]
        new = [_node(5, h, version_id=_V2)]
        diffs = diff_versions(old, new)
        assert diffs[0].old_position_index == 5
        assert diffs[0].new_position_index == 5


# ── MODIFIED detection ────────────────────────────────────────────────────────


class TestModifiedNodes:
    def test_same_position_different_hash_is_modified(self) -> None:
        old = [_node(0, _hash("OLD"))]
        new = [_node(0, _hash("NEW"), version_id=_V2)]
        diffs = diff_versions(old, new)
        assert len(diffs) == 1
        assert diffs[0].status == DiffStatus.MODIFIED
        assert diffs[0].old_position_index == 0
        assert diffs[0].new_position_index == 0

    def test_modified_node_carries_new_version_node(self) -> None:
        """NodeDiff.node must be the new version's node for MODIFIED."""
        old_node = _node(0, _hash("OLD"))
        new_node = _node(0, _hash("NEW"), version_id=_V2)
        diffs = diff_versions([old_node], [new_node])
        assert diffs[0].node.version_id == _V2

    def test_multiple_positions_all_modified(self) -> None:
        old = [_node(i, _hash(f"old{i}")) for i in range(4)]
        new = [_node(i, _hash(f"new{i}"), version_id=_V2) for i in range(4)]
        diffs = diff_versions(old, new)
        assert all(d.status == DiffStatus.MODIFIED for d in diffs)


# ── ADDED detection ───────────────────────────────────────────────────────────


class TestAddedNodes:
    def test_new_node_with_no_position_anchor_is_added(self) -> None:
        old = [_node(0, _hash("A"))]
        new = [_node(0, _hash("A"), version_id=_V2), _node(1, _hash("B"), version_id=_V2)]
        diffs = diff_versions(old, new)
        added = [d for d in diffs if d.status == DiffStatus.ADDED]
        assert len(added) == 1
        assert added[0].node.position_index == 1

    def test_added_node_has_no_old_position(self) -> None:
        new = [_node(0, _hash("BRAND_NEW"), version_id=_V2)]
        diffs = diff_versions([], new)
        assert diffs[0].old_position_index is None

    def test_added_node_has_new_position(self) -> None:
        new = [_node(7, _hash("BRAND_NEW"), version_id=_V2)]
        diffs = diff_versions([], new)
        assert diffs[0].new_position_index == 7


# ── DELETED detection ─────────────────────────────────────────────────────────


class TestDeletedNodes:
    def test_old_node_with_no_new_match_is_deleted(self) -> None:
        old = [_node(0, _hash("A")), _node(1, _hash("B"))]
        new = [_node(0, _hash("A"), version_id=_V2)]
        diffs = diff_versions(old, new)
        deleted = [d for d in diffs if d.status == DiffStatus.DELETED]
        assert len(deleted) == 1
        assert deleted[0].node.position_index == 1

    def test_deleted_node_carries_old_version_node(self) -> None:
        old_node = _node(0, _hash("GONE"))
        diffs = diff_versions([old_node], [])
        assert diffs[0].node.version_id == _V1

    def test_deleted_node_has_no_new_position(self) -> None:
        old = [_node(0, _hash("GONE"))]
        diffs = diff_versions(old, [])
        assert diffs[0].new_position_index is None


# ── MOVED detection ───────────────────────────────────────────────────────────


class TestMovedNodes:
    def test_same_hash_different_position_within_tolerance_is_moved(self) -> None:
        h = _hash("M")
        old = [_node(0, h)]
        new = [_node(2, h, version_id=_V2)]  # distance=2, tolerance=3
        diffs = diff_versions(old, new, tolerance=3)
        assert len(diffs) == 1
        assert diffs[0].status == DiffStatus.MOVED

    def test_moved_node_carries_new_version_node(self) -> None:
        h = _hash("N")
        old = [_node(0, h)]
        new = [_node(1, h, version_id=_V2)]
        diffs = diff_versions(old, new, tolerance=3)
        assert diffs[0].node.version_id == _V2

    def test_beyond_tolerance_not_moved(self) -> None:
        h = _hash("O")
        old = [_node(0, h)]
        new = [_node(10, h, version_id=_V2)]  # distance=10 >> tolerance=3
        diffs = diff_versions(old, new, tolerance=3)
        # Should be ADDED (new) + DELETED (old), not MOVED
        statuses = {d.status for d in diffs}
        assert DiffStatus.MOVED not in statuses
        assert DiffStatus.ADDED in statuses
        assert DiffStatus.DELETED in statuses


# ── Mixed scenario ────────────────────────────────────────────────────────────


class TestMixedScenario:
    """End-to-end scenario from the algorithm docstring."""

    def test_full_scenario(self) -> None:
        """
        old: A(0), B(1), C(2), D(3)
        new: A'(0), B(1), E(2), D(4)
          A' = same position, different hash  → MODIFIED
          B  = same position, same hash       → UNCHANGED
          E  = no match anywhere              → ADDED (C at 2 is old, different hash)
          D  = same hash, position 3→4        → MOVED (within tolerance=3)
          C  = not matched                    → DELETED
        """
        hash_a = _hash("A")
        hash_b = _hash("B")
        hash_c = _hash("C")
        hash_d = _hash("D")
        hash_ap = _hash("Z")  # A' (modified A)
        hash_e = _hash("E")   # E (brand new)

        old = [_node(0, hash_a), _node(1, hash_b), _node(2, hash_c), _node(3, hash_d)]
        new = [
            _node(0, hash_ap, version_id=_V2),  # A' modified
            _node(1, hash_b, version_id=_V2),   # B unchanged
            _node(2, hash_e, version_id=_V2),   # E — C is at old pos 2, E is new hash
            _node(4, hash_d, version_id=_V2),   # D moved (distance=1)
        ]

        diffs = diff_versions(old, new, tolerance=3)
        by_new_pos = {d.new_position_index: d for d in diffs if d.status != DiffStatus.DELETED}
        deleted = [d for d in diffs if d.status == DiffStatus.DELETED]

        assert by_new_pos[1].status == DiffStatus.UNCHANGED
        assert by_new_pos[0].status == DiffStatus.MODIFIED
        assert by_new_pos[4].status == DiffStatus.MOVED
        # E (new pos 2) is positionally anchored to C (old pos 2) → MODIFIED
        # C is consumed by the MODIFIED match, so it does NOT appear as DELETED
        assert by_new_pos[2].status == DiffStatus.MODIFIED
        assert by_new_pos[2].node.content_hash == hash_e  # new version's node
        # D is MOVED, not DELETED
        assert not any(d.node.content_hash == hash_d for d in deleted)

    def test_reupload_identical_document_zero_changes(self) -> None:
        """Re-uploading the identical file must produce zero diffs of any type
        except UNCHANGED.  This validates the idempotency guarantee."""
        hashes = [_hash(str(i)) for i in range(10)]
        old = [_node(i, hashes[i]) for i in range(10)]
        new = [_node(i, hashes[i], version_id=_V2) for i in range(10)]
        diffs = diff_versions(old, new)
        assert all(d.status == DiffStatus.UNCHANGED for d in diffs)
        assert len(diffs) == 10


# ── Output ordering ───────────────────────────────────────────────────────────


class TestOutputOrdering:
    def test_new_nodes_sorted_by_new_position_index(self) -> None:
        new = [_node(i, _hash(str(i)), version_id=_V2) for i in range(5)]
        diffs = diff_versions([], new)
        positions = [d.new_position_index for d in diffs]
        assert positions == sorted(positions)

    def test_deleted_nodes_sorted_after_new_nodes(self) -> None:
        old = [_node(0, _hash("DEL"))]
        new = [_node(1, _hash("NEW"), version_id=_V2)]
        diffs = diff_versions(old, new)
        # DELETED must appear after non-deleted
        last_non_deleted = max(
            (i for i, d in enumerate(diffs) if d.status != DiffStatus.DELETED),
            default=-1,
        )
        first_deleted = min(
            (i for i, d in enumerate(diffs) if d.status == DiffStatus.DELETED),
            default=len(diffs),
        )
        assert last_non_deleted < first_deleted


# ── Input validation ──────────────────────────────────────────────────────────


class TestInputValidation:
    def test_duplicate_position_in_old_raises(self) -> None:
        old = [_node(0, _hash("A")), _node(0, _hash("B"))]
        with pytest.raises(ValueError, match="Duplicate position_index"):
            diff_versions(old, [])

    def test_duplicate_position_in_new_raises(self) -> None:
        new = [_node(0, _hash("A"), version_id=_V2), _node(0, _hash("B"), version_id=_V2)]
        with pytest.raises(ValueError, match="Duplicate position_index"):
            diff_versions([], new)


# ── summarise_diff ────────────────────────────────────────────────────────────


class TestSummariseDiff:
    def test_empty_diffs_all_zero(self) -> None:
        counts = summarise_diff([])
        assert counts == {"unchanged": 0, "modified": 0, "added": 0, "deleted": 0, "moved": 0}

    def test_counts_match_actual_statuses(self) -> None:
        old = [_node(0, _hash("OLD")), _node(1, _hash("SAME")), _node(2, _hash("GONE"))]
        new = [_node(0, _hash("NEW"), version_id=_V2), _node(1, _hash("SAME"), version_id=_V2)]
        diffs = diff_versions(old, new)
        counts = summarise_diff(diffs)
        assert counts["modified"] == 1
        assert counts["unchanged"] == 1
        assert counts["deleted"] == 1
        assert counts["added"] == 0
        assert counts["moved"] == 0

    def test_all_keys_always_present(self) -> None:
        diffs = diff_versions([], [_node(0, _hash("X"), version_id=_V2)])
        counts = summarise_diff(diffs)
        assert set(counts.keys()) == {"unchanged", "modified", "added", "deleted", "moved"}

    def test_total_equals_sum_of_input_nodes(self) -> None:
        # Use unique seeds so hashes don't collide
        old_seeds = [f"old{i}" for i in range(5)]
        new_seeds = [f"new{i}" for i in range(3)]
        old = [_node(i, _hash(old_seeds[i])) for i in range(5)]
        new = [_node(i, _hash(new_seeds[i]), version_id=_V2) for i in range(3)]
        diffs = diff_versions(old, new)
        counts = summarise_diff(diffs)
        # Expect: 3 MODIFIED (positions 0,1,2 all changed) + 2 DELETED (positions 3,4)
        assert counts["modified"] == 3
        assert counts["deleted"] == 2
        assert counts["added"] == 0
        assert sum(counts.values()) == len(old)  # 5: 3 modified + 2 deleted


# ── Custom tolerance ──────────────────────────────────────────────────────────


class TestCustomTolerance:
    def test_tolerance_zero_strict_matching(self) -> None:
        h = _hash("T")
        old = [_node(0, h)]
        new = [_node(1, h, version_id=_V2)]
        diffs = diff_versions(old, new, tolerance=0)
        statuses = {d.status for d in diffs}
        # Distance 1 > tolerance 0 → no hash match → ADDED + DELETED
        assert DiffStatus.UNCHANGED not in statuses
        assert DiffStatus.MOVED not in statuses

    def test_large_tolerance_matches_distant_nodes(self) -> None:
        h = _hash("U")
        old = [_node(0, h)]
        new = [_node(20, h, version_id=_V2)]
        diffs = diff_versions(old, new, tolerance=25)
        assert len(diffs) == 1
        assert diffs[0].status == DiffStatus.MOVED
