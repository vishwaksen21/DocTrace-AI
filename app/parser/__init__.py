"""PDF parser subsystem package.

This package implements a five-pass extraction pipeline for digitally
generated PDFs (text-extractable, no OCR required).

Pass order:
    1. Structure extraction  — raw text blocks + bounding boxes (PyMuPDF)
    2. Heading detection     — font-heuristic heading classification
    3. Table extraction      — pdfplumber table → Markdown table format
    4. List detection        — regex-based bullet/numbered list recognition
    5. Hierarchy assembly    — parent-child tree, position_index, path

Public API::

    from app.parser import parse_pdf

    async def background_parse(path: Path, version_id: UUID) -> list[ParsedNode]:
        return await parse_pdf(path, version_id)

Design principles:
    - Each pass is a separate module with a single public function.
    - Passes are pure functions; no state leaks between passes.
    - The orchestrator (pdf_parser.py) is the only module that composes passes.
    - All intermediate data types are defined in this package.
    - OCR extensibility: insert an OCR pass between raw extraction and
      heading detection without changing any other module.
"""

from __future__ import annotations

from app.parser.pdf_parser import parse_pdf
from app.parser.types import ParsedNode

__all__ = ["ParsedNode", "parse_pdf"]
