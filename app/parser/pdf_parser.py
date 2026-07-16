"""PDF Parser orchestrator — composes all five extraction passes.

This is the single public entry point for the parsing subsystem.
Callers (document service layer) should import only this module:

    from app.parser.pdf_parser import parse_pdf

The function is ``async`` for API compatibility: the service layer
awaits it in a ``BackgroundTask``.  The heavy lifting (PyMuPDF, pdfplumber)
is CPU-bound; in production this should be executed in a thread pool via
``asyncio.to_thread`` to avoid blocking the event loop.  The function
wraps the synchronous parsing in ``asyncio.to_thread`` automatically.

Five-pass pipeline:
    1. ``structure_extractor.extract_blocks``    → list[RawBlock]
    2. ``heading_detector.detect_headings``      → list[(block, level, conf)]
    3. ``table_extractor.extract_tables``        → list[RawTable]
    4. Table suppression: mark blocks inside table bboxes
    5. ``hierarchy_builder.build_hierarchy``     → list[ParsedNode]
       + ``hierarchy_builder.assign_paths``      → paths filled in

Pass 4 (list detection) is embedded inside ``hierarchy_builder``
because list items are derived from classified paragraph blocks,
not raw blocks.

Error handling:
    - Empty PDF (no extractable text blocks): returns empty list with a
      warning log.  The service layer sets the version status to FAILED
      with ``error_message = "No extractable text found in PDF"``.
    - Corrupt/encrypted PDF: raises ``PDFParsingError`` which is caught by
      the background task and written to the version's ``error_message``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from app.domain.exceptions import PDFParsingError
from app.parser.heading_detector import detect_headings
from app.parser.hierarchy_builder import assign_paths, build_hierarchy
from app.parser.structure_extractor import extract_blocks
from app.parser.table_extractor import bbox_overlaps, extract_tables
from app.parser.types import ParsedNode, RawBlock, RawTable

logger = structlog.get_logger(__name__)


async def parse_pdf(source: Path | bytes, *, filename: str = "<upload>") -> list[ParsedNode]:
    """Parse a PDF and return an ordered list of structural nodes.

    The function is async and offloads blocking I/O to a thread pool via
    ``asyncio.to_thread`` so it does not block the FastAPI event loop.

    Args:
        source:   Path to a PDF file, or raw PDF bytes from an HTTP upload.
        filename: Original filename for error messages and log context.
                  Defaults to ``"<upload>"`` when bytes are passed.

    Returns:
        Ordered list of ``ParsedNode`` objects ready to be mapped to domain
        entities.  The list may be empty if the PDF contains no extractable
        text.

    Raises:
        PDFParsingError: If the PDF cannot be opened, is encrypted, or an
                         unrecoverable error occurs during extraction.
    """
    bound_logger = logger.bind(filename=filename)
    bound_logger.info("pdf_parser.started")

    try:
        nodes = await asyncio.to_thread(_parse_sync, source, filename)
    except PDFParsingError:
        raise
    except Exception as exc:
        raise PDFParsingError(filename=filename, reason=str(exc)) from exc

    bound_logger.info("pdf_parser.complete", total_nodes=len(nodes))
    return nodes


def _parse_sync(source: Path | bytes, filename: str) -> list[ParsedNode]:
    """Synchronous inner implementation — runs in a thread pool.

    Separated from ``parse_pdf`` so it can be called directly in synchronous
    tests without an event loop.

    Raises:
        PDFParsingError: On any unrecoverable parsing failure.
    """
    # ── Pass 1: Structure extraction ──────────────────────────────────────────
    try:
        raw_blocks: list[RawBlock] = extract_blocks(source)
    except ValueError as exc:
        raise PDFParsingError(filename=filename, reason=str(exc)) from exc

    if not raw_blocks:
        logger.warning(
            "pdf_parser.no_blocks_extracted", filename=filename
        )
        return []

    # ── Pass 2: Heading detection ─────────────────────────────────────────────
    heading_results = detect_headings(raw_blocks)

    # ── Pass 3: Table extraction ──────────────────────────────────────────────
    try:
        raw_tables: list[RawTable] = extract_tables(source)
    except ValueError as exc:
        # Table extraction failure is non-fatal: log and continue without tables.
        logger.warning(
            "pdf_parser.table_extraction_failed",
            filename=filename,
            reason=str(exc),
        )
        raw_tables = []

    # ── Pass 4: Table suppression ─────────────────────────────────────────────
    # Determine which raw blocks overlap with detected table bounding boxes.
    # These blocks will be skipped by the hierarchy builder to avoid
    # rendering table content twice (once as text, once as Markdown table).
    table_suppressed: set[int] = _compute_table_suppressed(raw_blocks, raw_tables)

    # ── Pass 5: Hierarchy assembly + path assignment ──────────────────────────
    nodes_without_paths = build_hierarchy(
        blocks=raw_blocks,
        heading_results=heading_results,
        tables=raw_tables,
        table_suppressed=table_suppressed,
    )
    nodes = assign_paths(nodes_without_paths)

    if not nodes:
        logger.warning(
            "pdf_parser.no_nodes_produced",
            filename=filename,
            raw_block_count=len(raw_blocks),
        )

    return nodes


def _compute_table_suppressed(
    raw_blocks: list[RawBlock],
    raw_tables: list[RawTable],
) -> set[int]:
    """Return the set of object IDs of RawBlocks that overlap a table bbox.

    Using ``id(block)`` (memory address) as the suppression key avoids
    adding an artificial sequential ID to RawBlock.

    Args:
        raw_blocks: All raw blocks from structure extraction.
        raw_tables: All tables from table extraction.

    Returns:
        Set of ``id(block)`` values for blocks that should be skipped.
    """
    if not raw_tables:
        return set()

    suppressed: set[int] = set()

    # Build a page → tables mapping to limit comparison to same-page blocks.
    page_tables: dict[int, list[RawTable]] = {}
    for tbl in raw_tables:
        page_tables.setdefault(tbl.page_number, []).append(tbl)

    for block in raw_blocks:
        tables_on_page = page_tables.get(block.page_number, [])
        for tbl in tables_on_page:
            if bbox_overlaps(block.bbox, tbl.bbox):
                suppressed.add(id(block))
                break

    return suppressed
