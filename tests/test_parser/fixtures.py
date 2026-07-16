"""Fixtures for the parser test suite.

Provides programmatically generated PDF bytes and helper factories
so tests never depend on binary fixture files stored in git.

Usage::

    from tests.test_parser.fixtures import (
        make_simple_pdf,
        make_multiheading_pdf,
        make_table_pdf,
        make_list_pdf,
    )
"""

from __future__ import annotations

import fitz  # PyMuPDF


def make_simple_pdf(
    text: str = "Hello World",
    font_size: float = 12.0,
) -> bytes:
    """Create a minimal single-page PDF with one text block.

    Args:
        text:       Text to embed.
        font_size:  Font size in points.

    Returns:
        Raw PDF bytes.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 100),
        text,
        fontsize=font_size,
    )
    return doc.tobytes()


def make_multiheading_pdf() -> bytes:
    """Create a PDF with H1, H2, and paragraph content for hierarchy tests.

    Structure:
        18pt bold: "Introduction"                 → H1 candidate
        14pt bold: "1.1 Background"               → H2 candidate
        10pt:      "This is body text."           → paragraph
        18pt bold: "Methods"                      → H1 candidate
        10pt:      "We used approach X."          → paragraph
    """
    doc = fitz.open()
    page = doc.new_page()

    def insert(y: float, text: str, size: float, bold: bool = False) -> None:
        font = "helv" if not bold else "hebo"
        page.insert_text((72, y), text, fontsize=size, fontname=font)

    insert(100, "Introduction", 18.0, bold=True)
    insert(130, "1.1 Background", 14.0, bold=True)
    insert(160, "This is body text.", 10.0)
    insert(200, "Methods", 18.0, bold=True)
    insert(230, "We used approach X.", 10.0)

    return doc.tobytes()


def make_list_pdf() -> bytes:
    """Create a PDF with a bullet list embedded in body text."""
    doc = fitz.open()
    page = doc.new_page()

    content = (
        "Requirements\n\n"
        "The system must support:\n\n"
        "- Fast uploads\n"
        "- Accurate parsing\n"
        "- Version diffing\n\n"
        "These are non-negotiable."
    )
    page.insert_text((72, 100), content, fontsize=11.0)
    return doc.tobytes()
