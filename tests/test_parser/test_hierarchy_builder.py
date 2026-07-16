"""Tests for app/parser/hierarchy_builder.py."""

from __future__ import annotations

from app.domain.enums import NodeType
from app.parser.hierarchy_builder import assign_paths, build_hierarchy
from app.parser.types import RawBlock

# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_HASH = "a" * 64


def _block(
    text: str,
    font_size: float = 10.0,
    is_bold: bool = False,
    idx: int = 0,
    page: int = 0,
) -> RawBlock:
    return RawBlock(
        page_number=page,
        block_index=idx,
        text=text,
        font_size=font_size,
        is_bold=is_bold,
        is_italic=False,
        bbox=(0.0, float(idx * 20), 500.0, float(idx * 20 + 18)),
        block_type=0,
    )


def _heading_result(block: RawBlock, level: int, conf: float = 0.95):
    return (block, level, conf)


def _para_result(block: RawBlock):
    return (block, None, 1.0)


class TestBuildHierarchy:
    """Tests for build_hierarchy() output structure."""

    def test_single_paragraph(self) -> None:
        b = _block("Hello world", idx=0)
        nodes = build_hierarchy([b], [_para_result(b)], [], set())
        assert len(nodes) == 1
        assert nodes[0].node_type == NodeType.PARAGRAPH
        assert nodes[0].content == "Hello world"

    def test_heading_before_paragraph(self) -> None:
        h = _block("Title", font_size=18.0, is_bold=True, idx=0)
        p = _block("Body text.", idx=1)
        blocks = [h, p]
        results = [_heading_result(h, 1), _para_result(p)]
        nodes = build_hierarchy(blocks, results, [], set())
        assert nodes[0].node_type == NodeType.HEADING
        assert nodes[0].heading_level == 1
        assert nodes[1].node_type == NodeType.PARAGRAPH
        assert nodes[1].parent_position_index == 0

    def test_h2_nested_under_h1(self) -> None:
        h1 = _block("Chapter 1", font_size=18.0, is_bold=True, idx=0)
        h2 = _block("Section 1.1", font_size=14.0, is_bold=True, idx=1)
        p = _block("Content.", idx=2)
        blocks = [h1, h2, p]
        results = [_heading_result(h1, 1), _heading_result(h2, 2), _para_result(p)]
        nodes = build_hierarchy(blocks, results, [], set())
        # h2 parent = h1 (pos 0)
        assert nodes[1].parent_position_index == 0
        # paragraph parent = h2 (pos 1)
        assert nodes[2].parent_position_index == 1

    def test_second_h1_resets_heading_stack(self) -> None:
        h1a = _block("Ch 1", font_size=18.0, is_bold=True, idx=0)
        h2 = _block("Sec 1.1", font_size=14.0, is_bold=True, idx=1)
        h1b = _block("Ch 2", font_size=18.0, is_bold=True, idx=2)
        p = _block("Body of Ch2.", idx=3)
        blocks = [h1a, h2, h1b, p]
        results = [
            _heading_result(h1a, 1),
            _heading_result(h2, 2),
            _heading_result(h1b, 1),
            _para_result(p),
        ]
        nodes = build_hierarchy(blocks, results, [], set())
        # paragraph at pos 3 should be child of h1b at pos 2
        assert nodes[3].parent_position_index == 2

    def test_position_index_sequential(self) -> None:
        blocks = [_block(f"b{i}", idx=i) for i in range(5)]
        results = [_para_result(b) for b in blocks]
        nodes = build_hierarchy(blocks, results, [], set())
        assert [n.position_index for n in nodes] == [0, 1, 2, 3, 4]

    def test_blank_blocks_skipped(self) -> None:
        b_blank = _block("   ", idx=0)
        b_text = _block("Real content", idx=1)
        results = [_para_result(b_blank), _para_result(b_text)]
        nodes = build_hierarchy([b_blank, b_text], results, [], set())
        assert len(nodes) == 1
        assert nodes[0].content == "Real content"

    def test_suppressed_block_skipped(self) -> None:
        b = _block("Table text overlap", idx=0)
        results = [_para_result(b)]
        nodes = build_hierarchy([b], results, [], table_suppressed={id(b)})
        assert len(nodes) == 0

    def test_list_block_expands_to_list_plus_items(self) -> None:
        # Provide a block with bullet list content
        b = _block("- Alpha\n- Beta\n- Gamma", idx=0)
        results = [_para_result(b)]
        nodes = build_hierarchy([b], results, [], set())
        # Should be: 1 LIST node + 3 LIST_ITEM nodes
        assert len(nodes) == 4
        assert nodes[0].node_type == NodeType.LIST
        assert all(n.node_type == NodeType.LIST_ITEM for n in nodes[1:])

    def test_list_items_have_list_as_parent(self) -> None:
        b = _block("- X\n- Y", idx=0)
        results = [_para_result(b)]
        nodes = build_hierarchy([b], results, [], set())
        for item in nodes[1:]:
            assert item.parent_position_index == 0  # LIST node is at pos 0

    def test_content_hash_is_64_chars(self) -> None:
        b = _block("Some text", idx=0)
        nodes = build_hierarchy([b], [_para_result(b)], [], set())
        for node in nodes:
            assert len(node.content_hash) == 64

    def test_empty_input_returns_empty_list(self) -> None:
        assert build_hierarchy([], [], [], set()) == []


class TestAssignPaths:
    """assign_paths() must compute correct materialized paths."""

    def test_single_root_node_path(self) -> None:
        b = _block("Root", idx=0)
        nodes = build_hierarchy([b], [_para_result(b)], [], set())
        final = assign_paths(nodes)
        assert final[0].path == "0"

    def test_two_root_nodes(self) -> None:
        b1 = _block("Root 1", idx=0)
        b2 = _block("Root 2", idx=1)
        nodes = build_hierarchy([b1, b2], [_para_result(b1), _para_result(b2)], [], set())
        final = assign_paths(nodes)
        assert final[0].path == "0"
        assert final[1].path == "1"

    def test_child_path_includes_parent_path(self) -> None:
        h = _block("Title", font_size=18.0, is_bold=True, idx=0)
        p = _block("Body.", idx=1)
        nodes = build_hierarchy([h, p], [_heading_result(h, 1), _para_result(p)], [], set())
        final = assign_paths(nodes)
        # h1 is root "0"; first child is "0.0"
        assert final[0].path == "0"
        assert final[1].path == "0.0"

    def test_sibling_paths_increment(self) -> None:
        h = _block("H1", font_size=18.0, is_bold=True, idx=0)
        p1 = _block("P1", idx=1)
        p2 = _block("P2", idx=2)
        nodes = build_hierarchy(
            [h, p1, p2],
            [_heading_result(h, 1), _para_result(p1), _para_result(p2)],
            [],
            set(),
        )
        final = assign_paths(nodes)
        assert final[1].path == "0.0"
        assert final[2].path == "0.1"

    def test_deep_nesting_path(self) -> None:
        h1 = _block("H1", font_size=18.0, is_bold=True, idx=0)
        h2 = _block("H2", font_size=14.0, is_bold=True, idx=1)
        p = _block("P", idx=2)
        nodes = build_hierarchy(
            [h1, h2, p],
            [_heading_result(h1, 1), _heading_result(h2, 2), _para_result(p)],
            [],
            set(),
        )
        final = assign_paths(nodes)
        assert final[2].path == "0.0.0"
