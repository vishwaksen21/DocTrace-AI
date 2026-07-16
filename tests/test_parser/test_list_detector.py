"""Tests for app/parser/list_detector.py."""

from __future__ import annotations

from app.domain.enums import NodeType
from app.parser.list_detector import detect_lists


class TestDetectLists:
    """detect_lists() returns None for non-list content, items for list content."""

    def test_bullet_list_detected(self) -> None:
        text = "- Item one\n- Item two\n- Item three"
        result = detect_lists(text)
        assert result is not None
        assert len(result) == 3
        assert all(i.node_type == NodeType.LIST_ITEM for i in result)

    def test_bullet_with_dash_detected(self) -> None:
        text = "- First\n- Second"
        assert detect_lists(text) is not None

    def test_bullet_with_dot(self) -> None:
        text = "• Alpha\n• Beta\n• Gamma"
        result = detect_lists(text)
        assert result is not None
        assert len(result) == 3

    def test_numbered_list_detected(self) -> None:
        text = "1. Introduction\n2. Methods\n3. Results"
        result = detect_lists(text)
        assert result is not None
        assert len(result) == 3

    def test_numbered_list_with_parens(self) -> None:
        text = "(1) First\n(2) Second\n(3) Third"
        result = detect_lists(text)
        assert result is not None
        assert len(result) == 3

    def test_single_item_returns_none(self) -> None:
        """One matching line is a false positive (e.g., '1. Introduction' heading)."""
        text = "1. Introduction"
        assert detect_lists(text) is None

    def test_plain_paragraph_returns_none(self) -> None:
        text = "This is a plain paragraph with no list markers."
        assert detect_lists(text) is None

    def test_empty_string_returns_none(self) -> None:
        assert detect_lists("") is None

    def test_multiline_item_merged(self) -> None:
        """A list item that wraps to the next line should be merged."""
        text = "- First item that is\n  quite long\n- Second item"
        result = detect_lists(text)
        assert result is not None
        assert len(result) == 2
        assert "First item that is" in result[0].text
        assert "quite long" in result[0].text

    def test_item_text_excludes_marker(self) -> None:
        text = "- Alpha\n- Beta"
        result = detect_lists(text)
        assert result is not None
        # Markers should not appear in the text
        assert not result[0].text.startswith("-")
        assert result[0].text.strip() == "Alpha"

    def test_marker_field_captured(self) -> None:
        text = "- Item one\n- Item two"
        result = detect_lists(text)
        assert result is not None
        assert result[0].marker == "-"

    def test_indent_level_zero_for_top_level(self) -> None:
        text = "- Top\n- Also top"
        result = detect_lists(text)
        assert result is not None
        assert result[0].indent_level == 0

    def test_mixed_content_non_list_returns_none(self) -> None:
        text = "Some intro text.\n\nMore text here without any list markers."
        assert detect_lists(text) is None
