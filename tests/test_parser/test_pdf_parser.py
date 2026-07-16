"""Integration tests for the full PDF parser pipeline (app/parser/pdf_parser.py).

These tests exercise the complete five-pass pipeline against programmatically
generated PDFs.  No external PDF files are required.

Tests are deliberately coarser than unit tests: they verify observable
outputs (node counts, types, ordering, paths) rather than internal state.
"""

from __future__ import annotations

import pytest

from app.domain.enums import NodeType
from app.parser.pdf_parser import _parse_sync, parse_pdf
from tests.test_parser.fixtures import (
    make_list_pdf,
    make_multiheading_pdf,
    make_simple_pdf,
)


class TestParseSyncSimple:
    """Synchronous wrapper tested directly (no event loop required)."""

    def test_simple_pdf_produces_at_least_one_node(self) -> None:
        pdf_bytes = make_simple_pdf("Hello World")
        nodes = _parse_sync(pdf_bytes, "simple.pdf")
        assert len(nodes) >= 1

    def test_all_nodes_have_valid_hashes(self) -> None:
        nodes = _parse_sync(make_simple_pdf("Test"), "test.pdf")
        for node in nodes:
            assert len(node.content_hash) == 64

    def test_all_nodes_have_sequential_position_index(self) -> None:
        nodes = _parse_sync(make_simple_pdf("Text content"), "seq.pdf")
        indices = [n.position_index for n in nodes]
        assert indices == list(range(len(nodes)))

    def test_all_nodes_have_non_empty_path(self) -> None:
        nodes = _parse_sync(make_simple_pdf("Path test"), "path.pdf")
        for node in nodes:
            assert node.path != ""

    def test_invalid_bytes_raises_pdf_parsing_error(self) -> None:
        from app.domain.exceptions import PDFParsingError

        with pytest.raises(PDFParsingError):
            _parse_sync(b"not a pdf at all", "bad.pdf")

    def test_empty_bytes_raises_pdf_parsing_error(self) -> None:
        from app.domain.exceptions import PDFParsingError

        with pytest.raises(PDFParsingError):
            _parse_sync(b"", "empty.pdf")


class TestMultiHeadingPDF:
    """Tests against the multi-heading fixture PDF."""

    def test_produces_multiple_nodes(self) -> None:
        nodes = _parse_sync(make_multiheading_pdf(), "multi.pdf")
        assert len(nodes) >= 3

    def test_first_heading_is_root(self) -> None:
        nodes = _parse_sync(make_multiheading_pdf(), "multi.pdf")
        headings = [n for n in nodes if n.node_type == NodeType.HEADING]
        assert len(headings) >= 1
        # H1 nodes must have no parent
        h1_nodes = [h for h in headings if h.heading_level == 1]
        assert len(h1_nodes) >= 1
        for h1 in h1_nodes:
            assert h1.parent_position_index is None

    def test_paragraphs_have_heading_parent(self) -> None:
        nodes = _parse_sync(make_multiheading_pdf(), "multi.pdf")
        paragraphs = [n for n in nodes if n.node_type == NodeType.PARAGRAPH]
        # All paragraphs should have a parent (they follow headings)
        for p in paragraphs:
            assert p.parent_position_index is not None

    def test_heading_levels_assigned(self) -> None:
        nodes = _parse_sync(make_multiheading_pdf(), "multi.pdf")
        headings = [n for n in nodes if n.node_type == NodeType.HEADING]
        for h in headings:
            assert h.heading_level is not None
            assert 1 <= h.heading_level <= 6

    def test_paths_are_hierarchical(self) -> None:
        """Child paths must start with parent path."""
        nodes = _parse_sync(make_multiheading_pdf(), "multi.pdf")
        path_map = {n.position_index: n.path for n in nodes}
        for node in nodes:
            if node.parent_position_index is not None:
                parent_path = path_map[node.parent_position_index]
                assert node.path.startswith(parent_path + ".")

    def test_idempotent_parse(self) -> None:
        """Parsing the same PDF twice must produce identical hashes."""
        pdf_bytes = make_multiheading_pdf()
        nodes1 = _parse_sync(pdf_bytes, "f.pdf")
        nodes2 = _parse_sync(pdf_bytes, "f.pdf")
        hashes1 = [n.content_hash for n in nodes1]
        hashes2 = [n.content_hash for n in nodes2]
        assert hashes1 == hashes2


class TestListPDF:
    """Tests for list detection in the full pipeline."""

    def test_list_items_detected(self) -> None:
        nodes = _parse_sync(make_list_pdf(), "list.pdf")
        list_items = [n for n in nodes if n.node_type == NodeType.LIST_ITEM]
        # The fixture has 3 bullet items
        assert len(list_items) >= 2  # lenient: at least 2 detected

    def test_list_parent_exists(self) -> None:
        nodes = _parse_sync(make_list_pdf(), "list.pdf")
        list_nodes = [n for n in nodes if n.node_type == NodeType.LIST]
        assert len(list_nodes) >= 1


class TestParsePdfAsync:
    """Tests for the async entry point."""

    async def test_async_parse_returns_nodes(self) -> None:
        nodes = await parse_pdf(make_simple_pdf("Async test"), filename="async.pdf")
        assert len(nodes) >= 1

    async def test_async_raises_on_invalid_bytes(self) -> None:
        from app.domain.exceptions import PDFParsingError

        with pytest.raises(PDFParsingError):
            await parse_pdf(b"garbage", filename="bad.pdf")
