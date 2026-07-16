"""Pass 2 — Heading detection.

Classifies raw text blocks as headings using a two-stage heuristic:

Stage A: Font-size heuristic
    Compares a block's font size to the document-wide body font size.
    Blocks significantly larger than body text are heading candidates.

Stage B: Numbered heading regex
    Blocks matching ``1.2.3 Title`` patterns are classified as headings
    regardless of font size, because technical documents often use
    numbered headings in body-text size.

Both stages produce a ``classification_confidence`` score (0.0-1.0).
Only blocks with confidence ≥ ``HEADING_MIN_CONFIDENCE`` (0.8 by default)
are classified as headings; the rest remain paragraphs.

Heading level assignment:
    H1-H6 levels are assigned by ranking unique font sizes in the document
    (largest → H1).  Numbered headings use the depth of their numbering
    (``1.`` → H1, ``1.2`` → H2, ``1.2.3`` → H3, etc.) as a cross-check.

This module is stateless and pure: given the same inputs it always
produces the same outputs.  No side effects.
"""

from __future__ import annotations

import re

import structlog

from app.core.constants import HEADING_MIN_CONFIDENCE, MAX_HEADING_DEPTH
from app.parser.types import RawBlock

logger = structlog.get_logger(__name__)

# Regex: matches "1.", "1.2", "1.2.3.4" optionally followed by a title.
# Capture group 1 = the numeric prefix (e.g. "1.2.3")
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\s*\.?\s+\S",
    re.MULTILINE,
)

# Font size ratio threshold above which a block is a heading candidate.
# e.g. 1.2 means "at least 20% larger than body font".
_FONT_RATIO_THRESHOLD: float = 1.20

# Confidence scores awarded by each signal
_CONFIDENCE_LARGE_FONT: float = 0.85
_CONFIDENCE_BOLD_LARGE_FONT: float = 0.95
_CONFIDENCE_NUMBERED: float = 0.90
_CONFIDENCE_BOLD_ONLY: float = 0.70  # below threshold; remains paragraph


def _body_font_size(blocks: list[RawBlock]) -> float:
    """Estimate the dominant body font size from a list of raw blocks.

    Uses character-weighted mode: the font size covering the most total
    characters is assumed to be body text.  This is robust against PDFs
    with many small footnotes or large display text.

    Returns 12.0 as a safe fallback if no text blocks are found.
    """
    size_counts: dict[float, int] = {}
    for block in blocks:
        if block.block_type != 0 or not block.text.strip():
            continue
        size_counts[block.font_size] = size_counts.get(block.font_size, 0) + len(
            block.text
        )
    if not size_counts:
        return 12.0
    return max(size_counts, key=lambda s: size_counts[s])


def _numbered_heading_depth(text: str) -> int | None:
    """Return the heading depth implied by a numbered prefix, or None.

    Examples:
        "1. Introduction"   → 1
        "2.3 Methods"       → 2
        "1.2.3.4 Sub-sub"   → 4 (capped at MAX_HEADING_DEPTH)
        "Introduction"      → None
    """
    first_line = text.split("\n")[0]
    match = _NUMBERED_HEADING_RE.match(first_line)
    if not match:
        return None
    depth = len(match.group(1).split("."))
    return min(depth, MAX_HEADING_DEPTH)


def _font_size_heading_level(font_size: float, size_ranking: list[float]) -> int:
    """Map a font size to a heading level using the document's size ranking.

    Args:
        font_size:    The block's dominant font size.
        size_ranking: Unique heading-candidate sizes sorted largest → smallest.

    Returns:
        Heading level 1-6 (clamped to MAX_HEADING_DEPTH).
    """
    try:
        rank = size_ranking.index(font_size)
    except ValueError:
        rank = len(size_ranking) - 1
    return min(rank + 1, MAX_HEADING_DEPTH)


def detect_headings(blocks: list[RawBlock]) -> list[tuple[RawBlock, int | None, float]]:
    """Classify blocks as headings and assign heading levels.

    For each block, returns a 3-tuple:
        - The original RawBlock (unmodified).
        - Heading level (1-6) if classified as a heading; None otherwise.
        - Classification confidence (0.0-1.0).

    Non-heading blocks are returned with heading_level=None and
    confidence=1.0 (they are confidently non-headings).

    Args:
        blocks: Ordered list of RawBlock objects from structure extraction.

    Returns:
        Same-length list of (block, heading_level, confidence) tuples.
    """
    body_size = _body_font_size(blocks)

    # Build the heading size ranking: all unique font sizes larger than body,
    # sorted largest first → maps to H1, H2, H3…
    heading_sizes = sorted(
        {
            b.font_size
            for b in blocks
            if b.block_type == 0
            and b.font_size > body_size * _FONT_RATIO_THRESHOLD
        },
        reverse=True,
    )

    results: list[tuple[RawBlock, int | None, float]] = []

    for block in blocks:
        if block.block_type != 0 or not block.text.strip():
            # Image blocks or blank text — never headings.
            results.append((block, None, 1.0))
            continue

        heading_level: int | None = None
        confidence: float = 0.0

        # Stage A: font-size heuristic
        if heading_sizes and block.font_size in heading_sizes:
            level_by_font = _font_size_heading_level(block.font_size, heading_sizes)
            if block.is_bold:
                confidence = _CONFIDENCE_BOLD_LARGE_FONT
            else:
                confidence = _CONFIDENCE_LARGE_FONT
            heading_level = level_by_font

        # Stage B: numbered heading regex (overrides Stage A level if found)
        numbered_depth = _numbered_heading_depth(block.text)
        if numbered_depth is not None:
            # Numbered headings get high confidence regardless of font size.
            if confidence < _CONFIDENCE_NUMBERED:
                confidence = _CONFIDENCE_NUMBERED
            heading_level = numbered_depth

        # Apply confidence threshold
        if confidence >= HEADING_MIN_CONFIDENCE and heading_level is not None:
            results.append((block, heading_level, confidence))
        else:
            if confidence > 0:
                # Below threshold: log the ambiguous block for observability.
                logger.debug(
                    "heading_detector.below_threshold",
                    page=block.page_number,
                    font_size=block.font_size,
                    confidence=round(confidence, 3),
                    text_preview=block.text[:60],
                )
            results.append((block, None, 1.0))

    return results
