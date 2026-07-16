"""Pass 5 — Hierarchy assembly.

Takes the classified nodes from Passes 1-4 and assembles them into a
proper parent-child tree, assigning ``position_index`` and materialized
``path`` to each node.

Algorithm
---------
The heading stack tracks the most recent heading at each depth level.
When a non-heading node is encountered, its parent is the most recent
heading on the stack (regardless of level).  When a heading is
encountered, the stack is truncated to the heading's level.

Example input order:
    pos 0: HEADING H1  ("1. Introduction")
    pos 1: PARAGRAPH   ("This chapter introduces…")
    pos 2: HEADING H2  ("1.1 Background")
    pos 3: PARAGRAPH   ("Historical context…")
    pos 4: HEADING H1  ("2. Methods")

Resulting tree:
    0 [H1]  path="0"
    └── 1 [P]   path="0.0"        parent=0
    └── 2 [H2]  path="0.1"        parent=0
        └── 3 [P]   path="0.1.0"  parent=2
    4 [H1]  path="1"
        (no children yet)

Materialized path:
    The path is the position_index of each ancestor separated by dots.
    This enables subtree queries with a single ``LIKE "0.1%"`` predicate.
    It is *not* the heading number — it is purely structural.

List grouping:
    When the list detector identifies list items in a block, the hierarchy
    builder inserts an implicit LIST parent node before the items.  The
    LIST node's content is the joined text of all items; the items become
    children.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.enums import NodeType
from app.parser.content_hasher import compute_hash
from app.parser.list_detector import DetectedListItem, detect_lists
from app.parser.types import ParsedNode, RawBlock, RawTable

logger = logging.getLogger(__name__)


def build_hierarchy(
    blocks: list[RawBlock],
    heading_results: list[tuple[RawBlock, int | None, float]],
    tables: list[RawTable],
    table_suppressed: set[int],  # block indices suppressed by table overlap
) -> list[ParsedNode]:
    """Assemble classified blocks and tables into an ordered node tree.

    Args:
        blocks:            Raw blocks from structure extraction.
        heading_results:   Parallel list of (block, heading_level, confidence)
                           from the heading detector.
        tables:            Raw tables from table extraction.
        table_suppressed:  Set of block indices (page-local) that overlap
                           with a detected table and should be skipped.

    Returns:
        Ordered list of ``ParsedNode`` objects with position_index, path,
        parent_position_index, and content_hash assigned.
    """
    # Merge text blocks and tables into a single chronological stream,
    # ordered by (page_number, block_index / y-position).
    items = _merge_stream(blocks, heading_results, tables, table_suppressed)

    nodes: list[ParsedNode] = []
    # heading_stack[i] = position_index of the most recent H(i+1) heading.
    # heading_stack has MAX_HEADING_DEPTH=6 slots.
    heading_stack: list[int | None] = [None] * 6
    position_index = 0

    for item in items:
        if item["kind"] == "table":
            node = _make_table_node(item, position_index, heading_stack)
            nodes.append(node)
            position_index += 1

        elif item["kind"] == "heading":
            level: int = item["heading_level"]
            node = _make_heading_node(item, position_index, heading_stack, level)
            # Update the heading stack: this heading becomes the parent for
            # subsequent nodes at deeper levels.
            heading_stack[level - 1] = position_index
            # Invalidate all deeper heading slots (they're now out of scope).
            for i in range(level, 6):
                heading_stack[i] = None
            nodes.append(node)
            position_index += 1

        elif item["kind"] == "list":
            items_for_list: list[DetectedListItem] = item["list_items"]
            position_index = _expand_list(
                items_for_list, item, nodes, position_index, heading_stack
            )

        else:  # paragraph
            node = _make_paragraph_node(item, position_index, heading_stack)
            nodes.append(node)
            position_index += 1

    logger.debug("hierarchy_builder.complete", total_nodes=len(nodes))
    return nodes


# ── Internal helpers ──────────────────────────────────────────────────────────


def _current_parent(heading_stack: list[int | None]) -> int | None:
    """Return the position_index of the nearest ancestor heading, or None."""
    for idx in reversed(range(6)):
        if heading_stack[idx] is not None:
            return heading_stack[idx]
    return None


def _build_path(parent_position: int | None, own_position: int, nodes: list[ParsedNode]) -> str:
    """Compute the materialized path for a node."""
    if parent_position is None:
        # Count existing root nodes to compute the root-level index.
        root_count = sum(1 for n in nodes if n.parent_position_index is None)
        return str(root_count)
    # Find parent node to get its path.
    parent_node = nodes[parent_position]
    child_count = sum(1 for n in nodes if n.parent_position_index == parent_position)
    return f"{parent_node.path}.{child_count}"


def _make_heading_node(
    item: dict[str, Any],
    position: int,
    heading_stack: list[int | None],
    level: int,
) -> ParsedNode:
    """Create a ParsedNode for a heading block."""
    # Parent = nearest heading at a shallower level
    parent_pos: int | None = None
    for i in range(level - 2, -1, -1):
        if heading_stack[i] is not None:
            parent_pos = heading_stack[i]
            break

    content = item["text"]
    return ParsedNode(
        node_type=NodeType.HEADING,
        content=content,
        content_hash=compute_hash(content),
        position_index=position,
        path="",  # filled below
        heading_level=level,
        parent_position_index=parent_pos,
        classification_confidence=item["confidence"],
        raw_metadata=item.get("raw_metadata", {}),
    )


def _make_paragraph_node(
    item: dict[str, Any],
    position: int,
    heading_stack: list[int | None],
) -> ParsedNode:
    parent_pos = _current_parent(heading_stack)
    content = item["text"]
    return ParsedNode(
        node_type=NodeType.PARAGRAPH,
        content=content,
        content_hash=compute_hash(content),
        position_index=position,
        path="",  # filled below
        parent_position_index=parent_pos,
        raw_metadata=item.get("raw_metadata", {}),
    )


def _make_table_node(
    item: dict[str, Any],
    position: int,
    heading_stack: list[int | None],
) -> ParsedNode:
    parent_pos = _current_parent(heading_stack)
    content = item["markdown"]
    return ParsedNode(
        node_type=NodeType.TABLE,
        content=content,
        content_hash=compute_hash(content),
        position_index=position,
        path="",  # filled below
        parent_position_index=parent_pos,
        raw_metadata=item.get("raw_metadata", {}),
    )


def _expand_list(
    list_items: list[DetectedListItem],
    item: dict[str, Any],
    nodes: list[ParsedNode],
    position: int,
    heading_stack: list[int | None],
) -> int:
    """Insert an implicit LIST node followed by LIST_ITEM children.

    Returns the next available position_index after all items are inserted.
    """
    parent_pos = _current_parent(heading_stack)
    joined_content = "\n".join(li.text for li in list_items)

    list_node = ParsedNode(
        node_type=NodeType.LIST,
        content=joined_content,
        content_hash=compute_hash(joined_content),
        position_index=position,
        path="",
        parent_position_index=parent_pos,
        raw_metadata=item.get("raw_metadata", {}),
    )
    nodes.append(list_node)
    list_position = position
    position += 1

    for li in list_items:
        item_node = ParsedNode(
            node_type=NodeType.LIST_ITEM,
            content=li.text,
            content_hash=compute_hash(li.text),
            position_index=position,
            path="",
            parent_position_index=list_position,
            raw_metadata={"marker": li.marker, "indent_level": li.indent_level},
        )
        nodes.append(item_node)
        position += 1

    return position


def _merge_stream(
    blocks: list[RawBlock],
    heading_results: list[tuple[RawBlock, int | None, float]],
    tables: list[RawTable],
    table_suppressed: set[int],
) -> list[dict[str, Any]]:
    """Merge text blocks and tables into a single sorted stream.

    Both sources are sorted by (page_number, y-position / block_index).
    Table bboxes that occupy a vertical range are interleaved at their
    top-y position.

    Returns:
        List of dicts with keys:
            kind: "heading" | "paragraph" | "table" | "list"
            text: block text (for non-table items)
            heading_level: int | None
            confidence: float
            raw_metadata: dict
            markdown: str (table only)
            list_items: list[DetectedListItem] (list only)
    """
    stream: list[dict[str, Any]] = []

    # Build a page → tables mapping for quick lookup
    page_tables: dict[int, list[RawTable]] = {}
    for t in tables:
        page_tables.setdefault(t.page_number, []).append(t)
    for tlist in page_tables.values():
        tlist.sort(key=lambda t: t.bbox[1])

    inserted_tables: set[id] = set()

    for (block, heading_level, confidence) in heading_results:
        # Skip suppressed blocks (overlap with table)
        if id(block) in table_suppressed:
            continue
        if block.block_type == 1:
            continue  # image block
        text = block.text.strip()
        if not text:
            continue

        # Before inserting this block, check if any table on the same page
        # appears before it (lower y than block top).
        page_t = page_tables.get(block.page_number, [])
        block_top_y = block.bbox[1]
        for tbl in page_t:
            if id(tbl) not in inserted_tables and tbl.bbox[1] < block_top_y:
                stream.append(_table_item(tbl))
                inserted_tables.add(id(tbl))

        raw_meta = {
            "page_number": block.page_number,
            "block_index": block.block_index,
            "font_size": block.font_size,
            "bbox": block.bbox,
        }

        if heading_level is not None:
            stream.append(
                {
                    "kind": "heading",
                    "text": text,
                    "heading_level": heading_level,
                    "confidence": confidence,
                    "raw_metadata": raw_meta,
                }
            )
        else:
            # Check for list items
            list_items = detect_lists(text)
            if list_items:
                stream.append(
                    {
                        "kind": "list",
                        "text": text,
                        "list_items": list_items,
                        "raw_metadata": raw_meta,
                    }
                )
            else:
                stream.append(
                    {
                        "kind": "paragraph",
                        "text": text,
                        "raw_metadata": raw_meta,
                    }
                )

    # Append any remaining tables that come after all text blocks on their page.
    for tbl in tables:
        if id(tbl) not in inserted_tables:
            stream.append(_table_item(tbl))

    return stream


def _table_item(tbl: RawTable) -> dict[str, Any]:
    try:
        markdown = tbl.to_markdown()
    except ValueError:
        markdown = ""
    return {
        "kind": "table",
        "markdown": markdown,
        "raw_metadata": {
            "page_number": tbl.page_number,
            "block_index": tbl.block_index,
            "bbox": tbl.bbox,
        },
    }


def assign_paths(nodes: list[ParsedNode]) -> list[ParsedNode]:
    """Assign materialized paths to all nodes in the list.

    This is a separate function called after ``build_hierarchy`` because
    path computation requires knowing the final position of each node in
    the flat list.

    Args:
        nodes: Ordered list of ParsedNode objects with paths = "".

    Returns:
        New list of ParsedNode objects with paths filled in.  The original
        list is not modified (frozen dataclasses cannot be mutated in-place;
        we use ``dataclasses.replace``).
    """
    import dataclasses

    path_map: dict[int, str] = {}  # position_index → path
    # Count children per parent to generate sequential sibling indices.
    child_count: dict[int | None, int] = {}

    result: list[ParsedNode] = []
    for node in nodes:
        parent = node.parent_position_index
        sibling_idx = child_count.get(parent, 0)
        child_count[parent] = sibling_idx + 1

        if parent is None:
            path = str(sibling_idx)
        else:
            parent_path = path_map[parent]
            path = f"{parent_path}.{sibling_idx}"

        path_map[node.position_index] = path
        result.append(dataclasses.replace(node, path=path))

    return result
