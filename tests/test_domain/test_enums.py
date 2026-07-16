"""Tests for app/domain/enums.py."""

from __future__ import annotations

from app.domain.enums import (
    DiffStatus,
    GenerationStatus,
    NodeType,
    VersionStatus,
)


class TestNodeType:
    """NodeType is a StrEnum — members serialize to lowercase string values."""

    def test_members_are_strings(self) -> None:
        assert isinstance(NodeType.HEADING, str)

    def test_string_value_equals_member_name_lower(self) -> None:
        assert NodeType.HEADING == "heading"
        assert NodeType.PARAGRAPH == "paragraph"
        assert NodeType.TABLE == "table"
        assert NodeType.LIST == "list"
        assert NodeType.LIST_ITEM == "list_item"

    def test_equality_with_string(self) -> None:
        assert NodeType.HEADING == "heading"
        assert "heading" == NodeType.HEADING

    def test_all_five_members_exist(self) -> None:
        expected = {"heading", "paragraph", "table", "list", "list_item"}
        assert {m.value for m in NodeType} == expected

    def test_roundtrip_from_string(self) -> None:
        assert NodeType("heading") is NodeType.HEADING
        assert NodeType("list_item") is NodeType.LIST_ITEM


class TestVersionStatus:
    """VersionStatus: PROCESSING → READY or FAILED."""

    def test_all_three_members_exist(self) -> None:
        expected = {"processing", "ready", "failed"}
        assert {m.value for m in VersionStatus} == expected

    def test_processing_is_initial_state_by_convention(self) -> None:
        # The first member is the initial state used at INSERT time
        members = list(VersionStatus)
        assert members[0] == VersionStatus.PROCESSING

    def test_roundtrip(self) -> None:
        assert VersionStatus("ready") is VersionStatus.READY


class TestDiffStatus:
    """DiffStatus used by the diff engine; all five variants must be present."""

    def test_all_five_members_exist(self) -> None:
        expected = {"unchanged", "modified", "added", "deleted", "moved"}
        assert {m.value for m in DiffStatus} == expected

    def test_string_comparison_works(self) -> None:
        assert DiffStatus.UNCHANGED == "unchanged"


class TestGenerationStatus:
    """GenerationStatus for LLM job tracking."""

    def test_all_four_members_exist(self) -> None:
        expected = {"processing", "success", "partial", "failed"}
        assert {m.value for m in GenerationStatus} == expected

    def test_processing_is_first_member(self) -> None:
        assert next(iter(GenerationStatus)) == GenerationStatus.PROCESSING
