"""Tests for app/domain/entities.py."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.domain.entities import (
    Document,
    GenerationResult,
    Node,
    NodeDiff,
    QATestCase,
    Selection,
    Version,
)
from app.domain.enums import (
    DiffStatus,
    GenerationStatus,
    NodeType,
    VersionStatus,
)

# ── Shared fixtures ────────────────────────────────────────────────────────────

NOW = datetime.now(tz=UTC)
DOC_ID = uuid.uuid4()
VER_ID = uuid.uuid4()
NODE_ID = uuid.uuid4()
SEL_ID = uuid.uuid4()

VALID_HASH = "a" * 64  # 64-char SHA-256 placeholder


def _make_node(**overrides) -> Node:
    """Helper that creates a valid PARAGRAPH node, accepting field overrides."""
    defaults = dict(
        id=NODE_ID,
        version_id=VER_ID,
        node_type=NodeType.PARAGRAPH,
        content="Sample content",
        content_hash=VALID_HASH,
        position_index=0,
        path="0",
        created_at=NOW,
    )
    defaults.update(overrides)
    return Node(**defaults)


def _make_version(**overrides) -> Version:
    defaults = dict(
        id=VER_ID,
        document_id=DOC_ID,
        version_number=1,
        upload_filename="report.pdf",
        status=VersionStatus.READY,
        created_at=NOW,
    )
    defaults.update(overrides)
    return Version(**defaults)


# ── Document ──────────────────────────────────────────────────────────────────


class TestDocument:
    def test_construction(self) -> None:
        doc = Document(
            id=DOC_ID,
            title="My Doc",
            original_filename="my_doc.pdf",
            created_at=NOW,
            updated_at=NOW,
        )
        assert doc.title == "My Doc"
        assert doc.id == DOC_ID

    def test_is_frozen(self) -> None:
        doc = Document(
            id=DOC_ID,
            title="T",
            original_filename="f.pdf",
            created_at=NOW,
            updated_at=NOW,
        )
        with pytest.raises((AttributeError, TypeError)):
            doc.title = "mutated"  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        d1 = Document(DOC_ID, "T", "f.pdf", NOW, NOW)
        d2 = Document(DOC_ID, "T", "f.pdf", NOW, NOW)
        assert d1 == d2


# ── Version ───────────────────────────────────────────────────────────────────


class TestVersion:
    def test_is_ready_property(self) -> None:
        v = _make_version(status=VersionStatus.READY)
        assert v.is_ready is True
        assert v.is_processing is False

    def test_is_processing_property(self) -> None:
        v = _make_version(status=VersionStatus.PROCESSING)
        assert v.is_processing is True
        assert v.is_ready is False

    def test_error_message_defaults_to_none(self) -> None:
        v = _make_version()
        assert v.error_message is None

    def test_error_message_can_be_set(self) -> None:
        v = _make_version(status=VersionStatus.FAILED, error_message="decrypt error")
        assert v.error_message == "decrypt error"


# ── Node ──────────────────────────────────────────────────────────────────────


class TestNode:
    def test_valid_paragraph_node(self) -> None:
        node = _make_node()
        assert node.node_type == NodeType.PARAGRAPH
        assert node.heading_level is None

    def test_valid_heading_node(self) -> None:
        node = _make_node(
            node_type=NodeType.HEADING,
            heading_level=2,
        )
        assert node.heading_level == 2

    def test_heading_without_level_raises(self) -> None:
        with pytest.raises(ValueError, match="heading_level must be set"):
            _make_node(node_type=NodeType.HEADING, heading_level=None)

    def test_non_heading_with_level_raises(self) -> None:
        with pytest.raises(ValueError, match="heading_level must be None"):
            _make_node(node_type=NodeType.PARAGRAPH, heading_level=1)

    def test_invalid_heading_level_raises(self) -> None:
        with pytest.raises(ValueError, match=r"1-6"):
            _make_node(node_type=NodeType.HEADING, heading_level=7)

    def test_heading_level_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            _make_node(node_type=NodeType.HEADING, heading_level=0)

    def test_short_content_hash_raises(self) -> None:
        with pytest.raises(ValueError, match="content_hash"):
            _make_node(content_hash="abc")  # too short

    def test_exactly_64_char_hash_is_accepted(self) -> None:
        node = _make_node(content_hash="f" * 64)
        assert len(node.content_hash) == 64

    def test_node_with_parent_id(self) -> None:
        parent_id = uuid.uuid4()
        node = _make_node(parent_id=parent_id)
        assert node.parent_id == parent_id

    def test_node_is_frozen(self) -> None:
        node = _make_node()
        with pytest.raises((AttributeError, TypeError)):
            node.content = "mutated"  # type: ignore[misc]


# ── NodeDiff ──────────────────────────────────────────────────────────────────


class TestNodeDiff:
    def test_unchanged_node_diff(self) -> None:
        node = _make_node()
        diff = NodeDiff(
            node=node,
            status=DiffStatus.UNCHANGED,
            old_position_index=0,
            new_position_index=0,
        )
        assert diff.status == DiffStatus.UNCHANGED

    def test_added_node_has_no_old_position(self) -> None:
        node = _make_node()
        diff = NodeDiff(node=node, status=DiffStatus.ADDED, new_position_index=5)
        assert diff.old_position_index is None


# ── Selection ─────────────────────────────────────────────────────────────────


class TestSelection:
    def test_valid_selection(self) -> None:
        node_ids = (uuid.uuid4(), uuid.uuid4())
        sel = Selection(
            id=SEL_ID,
            version_id=VER_ID,
            node_ids=node_ids,
            created_at=NOW,
        )
        assert len(sel.node_ids) == 2

    def test_empty_node_ids_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one node"):
            Selection(
                id=SEL_ID,
                version_id=VER_ID,
                node_ids=(),
                created_at=NOW,
            )

    def test_name_defaults_to_none(self) -> None:
        sel = Selection(SEL_ID, VER_ID, (uuid.uuid4(),), NOW)
        assert sel.name is None

    def test_node_ids_is_tuple(self) -> None:
        """node_ids must be a tuple (not list) because the entity is frozen."""
        node_ids = (uuid.uuid4(),)
        sel = Selection(SEL_ID, VER_ID, node_ids, NOW)
        assert isinstance(sel.node_ids, tuple)


# ── GenerationResult ──────────────────────────────────────────────────────────


class TestGenerationResult:
    def _make_result(self, **overrides) -> GenerationResult:
        tc = QATestCase(
            id="tc-001",
            title="Check login",
            objective="Verify login flow",
            preconditions=("User exists",),
            steps=("Open app", "Enter credentials"),
            expected_result="Dashboard shown",
        )
        defaults = dict(
            selection_id=SEL_ID,
            document_id=DOC_ID,
            version_id=VER_ID,
            model="google/gemini-2.5-flash",
            prompt_tokens=100,
            completion_tokens=200,
            status=GenerationStatus.SUCCESS,
            raw_response='{"test_cases": []}',
            test_cases=(tc,),
            validation_errors=(),
            created_at=NOW,
            duration_ms=1500.0,
        )
        defaults.update(overrides)
        return GenerationResult(**defaults)

    def test_total_tokens_property(self) -> None:
        result = self._make_result(prompt_tokens=100, completion_tokens=200)
        assert result.total_tokens == 300

    def test_id_defaults_to_none(self) -> None:
        result = self._make_result()
        assert result.id is None

    def test_to_mongo_doc_serializes_uuids_as_strings(self) -> None:
        result = self._make_result()
        doc = result.to_mongo_doc()
        assert isinstance(doc["selection_id"], str)
        assert isinstance(doc["document_id"], str)
        assert isinstance(doc["version_id"], str)

    def test_to_mongo_doc_serializes_test_cases(self) -> None:
        result = self._make_result()
        doc = result.to_mongo_doc()
        assert len(doc["test_cases"]) == 1
        tc = doc["test_cases"][0]
        assert tc["id"] == "tc-001"
        assert isinstance(tc["steps"], list)  # tuples → lists for BSON

    def test_to_mongo_doc_contains_status_string(self) -> None:
        result = self._make_result(status=GenerationStatus.SUCCESS)
        doc = result.to_mongo_doc()
        assert doc["status"] == "success"
