"""Pass 4 — List detection using regex pattern matching.

Identifies list items within text blocks that were classified as
plain paragraphs after Passes 1-3.  List items are re-tagged as
``NodeType.LIST_ITEM`` and grouped under implicit ``NodeType.LIST``
parent nodes.

Detection patterns:
    Bullet lists:   Lines starting with ``*``, ``-``, ``*``, ``-``, ``+``, ``o``
    Numbered lists: Lines starting with ``N.``, ``N)``, ``(N)`` where N is a digit
    Lettered lists: Lines starting with ``a.``, ``b)``, ``(a)`` (lowercase only)

Multi-line list items:
    A list item continues until the next line matches a list prefix or
    the block ends.  Continuation lines (no prefix) are merged into the
    previous item separated by a space.

Design decision — not splitting blocks:
    This pass operates on the *content* of existing RawBlocks, not the
    block list itself.  It returns a mapping from block index to detected
    list items.  The orchestrator is responsible for splitting blocks and
    creating new ParsedNodes.  This keeps the pass pure and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.enums import NodeType

# ── List-item prefix patterns ─────────────────────────────────────────────────

_BULLET_PATTERN = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<marker>[\u2022\-\*\u2013\u25aa\u25e6\u25e6])\s+"
    r"(?P<text>.+)$",
    re.UNICODE,
)

_NUMBERED_PATTERN = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<marker>\d+[.)]\s*|\(\d+\)\s*)"
    r"(?P<text>.+)$",
)

_LETTERED_PATTERN = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<marker>[a-z][.)]\s*|\([a-z]\)\s*)"
    r"(?P<text>.+)$",
)

_ALL_PATTERNS = [_BULLET_PATTERN, _NUMBERED_PATTERN, _LETTERED_PATTERN]


@dataclass
class DetectedListItem:
    """A single list item detected within a text block.

    Attributes:
        node_type:    Always ``NodeType.LIST_ITEM``.
        text:         Merged text of the list item (may span multiple source lines).
        indent_level: Nesting depth based on leading whitespace (0 = top-level).
        marker:       The original list marker string (e.g. ``"-"``, ``"1."``).
    """

    node_type: NodeType
    text: str
    indent_level: int
    marker: str


def detect_lists(text: str) -> list[DetectedListItem] | None:
    """Detect list items within a block's text content.

    Args:
        text: Raw text content of a single block.

    Returns:
        A list of ``DetectedListItem`` objects if at least two list items
        are found (a single matching line is assumed to be a false positive
        such as a "1. Introduction" section heading); None otherwise.

    Notes:
        - A minimum of 2 list items is required to avoid false positives
          from numbered headings that were not caught by the heading detector.
        - Multi-line items: continuation lines (not matching any list prefix)
          are appended to the current item's text.
    """
    lines = text.split("\n")
    items: list[DetectedListItem] = []
    current_item: DetectedListItem | None = None

    for line in lines:
        matched = _match_list_prefix(line)
        if matched:
            if current_item is not None:
                items.append(current_item)
            current_item = matched
        elif current_item is not None and line.strip():
            # Continuation of the current item
            current_item = DetectedListItem(
                node_type=NodeType.LIST_ITEM,
                text=current_item.text + " " + line.strip(),
                indent_level=current_item.indent_level,
                marker=current_item.marker,
            )
        # Blank lines while in a list item — end current item
        elif current_item is not None and not line.strip():
            items.append(current_item)
            current_item = None

    if current_item is not None:
        items.append(current_item)

    # Require at least 2 items to avoid false positives.
    if len(items) < 2:
        return None

    return items


def _match_list_prefix(line: str) -> DetectedListItem | None:
    """Try to match ``line`` against all list-item patterns.

    Returns a ``DetectedListItem`` on the first match, or None.
    Indent level is estimated by counting leading spaces // 2.
    """
    for pattern in _ALL_PATTERNS:
        m = pattern.match(line)
        if m:
            indent = len(m.group("indent"))
            return DetectedListItem(
                node_type=NodeType.LIST_ITEM,
                text=m.group("text").strip(),
                indent_level=indent // 2,
                marker=m.group("marker").strip(),
            )
    return None
