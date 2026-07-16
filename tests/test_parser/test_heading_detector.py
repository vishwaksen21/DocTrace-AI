"""Tests for app/parser/heading_detector.py."""

from __future__ import annotations

from app.parser.heading_detector import (
    _body_font_size,
    _numbered_heading_depth,
    detect_headings,
)
from app.parser.types import RawBlock

# ── RawBlock factory helper ───────────────────────────────────────────────────


def _block(
    text: str,
    font_size: float = 10.0,
    is_bold: bool = False,
    is_italic: bool = False,
    page: int = 0,
    idx: int = 0,
) -> RawBlock:
    return RawBlock(
        page_number=page,
        block_index=idx,
        text=text,
        font_size=font_size,
        is_bold=is_bold,
        is_italic=is_italic,
        bbox=(0, float(idx * 20), 500, float(idx * 20 + 18)),
        block_type=0,
    )


# ── _body_font_size ───────────────────────────────────────────────────────────


class TestBodyFontSize:
    def test_single_font_size(self) -> None:
        blocks = [_block("text", font_size=11.0)]
        assert _body_font_size(blocks) == 11.0

    def test_most_common_size_wins(self) -> None:
        """Body text covers most characters; heading is few characters."""
        blocks = [
            _block("A" * 200, font_size=10.0),  # lots of body text
            _block("Title", font_size=18.0),  # short heading
        ]
        assert _body_font_size(blocks) == 10.0

    def test_no_text_blocks_returns_fallback(self) -> None:
        blocks = [
            RawBlock(0, 0, "", 0.0, False, False, (0, 0, 100, 100), block_type=1),
        ]
        assert _body_font_size(blocks) == 12.0

    def test_empty_list_returns_fallback(self) -> None:
        assert _body_font_size([]) == 12.0

    def test_blank_text_blocks_ignored(self) -> None:
        blocks = [_block("   ", font_size=10.0), _block("content", font_size=12.0)]
        assert _body_font_size(blocks) == 12.0


# ── _numbered_heading_depth ───────────────────────────────────────────────────


class TestNumberedHeadingDepth:
    def test_single_number_is_h1(self) -> None:
        assert _numbered_heading_depth("1. Introduction") == 1

    def test_two_level_is_h2(self) -> None:
        assert _numbered_heading_depth("1.2 Background") == 2

    def test_three_level_is_h3(self) -> None:
        assert _numbered_heading_depth("1.2.3 Detail") == 3

    def test_plain_text_returns_none(self) -> None:
        assert _numbered_heading_depth("Introduction") is None

    def test_paragraph_text_returns_none(self) -> None:
        assert _numbered_heading_depth("This is a sentence.") is None

    def test_depth_capped_at_max(self) -> None:
        # 7 levels → capped at MAX_HEADING_DEPTH (6)
        assert _numbered_heading_depth("1.2.3.4.5.6.7 Deep") == 6

    def test_multiline_checks_first_line_only(self) -> None:
        text = "2.1 Summary\nThis is the body of the section."
        assert _numbered_heading_depth(text) == 2

    def test_number_without_text_after_returns_none(self) -> None:
        """A bare number like "1." with nothing after it is not a heading."""
        assert _numbered_heading_depth("1.") is None


# ── detect_headings ───────────────────────────────────────────────────────────


class TestDetectHeadings:
    """Integration tests for the full detection pipeline."""

    def test_large_bold_font_classified_as_heading(self) -> None:
        """A block with font size >> body and bold should be H1."""
        blocks = [
            _block("body " * 50, font_size=10.0, idx=0),  # body baseline
            _block("Big Title", font_size=20.0, is_bold=True, idx=1),
        ]
        results = detect_headings(blocks)
        _, level, confidence = results[1]
        assert level == 1
        assert confidence >= 0.8

    def test_body_text_not_classified_as_heading(self) -> None:
        blocks = [
            _block("body " * 50, font_size=10.0, idx=0),
            _block("Also body text.", font_size=10.0, idx=1),
        ]
        results = detect_headings(blocks)
        _, level, _ = results[1]
        assert level is None

    def test_numbered_heading_classified_regardless_of_font(self) -> None:
        """Even body-size numbered headings must be classified."""
        blocks = [
            _block("body " * 50, font_size=10.0, idx=0),
            _block("1.2 Section Name", font_size=10.0, idx=1),  # same size, numbered
        ]
        results = detect_headings(blocks)
        _, level, confidence = results[1]
        assert level == 2
        assert confidence >= 0.8

    def test_image_blocks_never_headings(self) -> None:
        image_block = RawBlock(0, 0, "", 18.0, True, False, (0, 0, 200, 200), block_type=1)
        results = detect_headings([image_block])
        _, level, _ = results[0]
        assert level is None

    def test_blank_text_never_heading(self) -> None:
        blocks = [_block("   ", font_size=18.0, is_bold=True)]
        _, level, _ = detect_headings(blocks)[0]
        assert level is None

    def test_multiple_heading_levels_ranked_correctly(self) -> None:
        """Larger font → lower heading level number (H1 < H2)."""
        blocks = [
            _block("body " * 50, font_size=10.0, idx=0),
            _block("Big", font_size=20.0, is_bold=True, idx=1),
            _block("Medium", font_size=16.0, is_bold=True, idx=2),
        ]
        results = detect_headings(blocks)
        _, h1_level, _ = results[1]
        _, h2_level, _ = results[2]
        assert h1_level == 1
        assert h2_level == 2

    def test_output_length_equals_input_length(self) -> None:
        blocks = [_block(f"block {i}", idx=i) for i in range(5)]
        results = detect_headings(blocks)
        assert len(results) == 5

    def test_below_confidence_threshold_returns_paragraph(self) -> None:
        """A bold-only block (no large font, no numbered prefix) stays paragraph."""
        blocks = [
            _block("body " * 50, font_size=10.0, idx=0),
            _block("Bold but small", font_size=10.0, is_bold=True, idx=1),
        ]
        results = detect_headings(blocks)
        _, level, _ = results[1]
        assert level is None
