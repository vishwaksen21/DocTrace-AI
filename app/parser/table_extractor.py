"""Pass 3 — Table extraction using pdfplumber.

pdfplumber's grid-detection algorithm is significantly more accurate than
PyMuPDF's for identifying table cells, especially in PDFs with borderless
or partially-bordered tables.  This pass is therefore separate from Pass 1
and uses pdfplumber exclusively.

Relationship with Pass 1:
    - Pass 1 (PyMuPDF) extracts text blocks globally.
    - Pass 3 (pdfplumber) extracts tables and their bounding boxes.
    - The orchestrator merges the two outputs: text blocks whose bounding
      box overlaps a pdfplumber-detected table are suppressed so that the
      table's Markdown representation is used instead.

Output:
    Each table becomes a single ``RawTable`` object.  The orchestrator
    converts it to a ``ParsedNode`` of type ``NodeType.TABLE`` with content
    in Markdown table format.

Limitation:
    Tables spanning multiple pages are partially supported: pdfplumber
    extracts each page's portion independently.  The orchestrator assigns
    each portion a separate node with ``raw_metadata["is_table_continuation"]``
    set to True for all pages after the first.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import structlog

from app.parser.types import RawTable

logger = structlog.get_logger(__name__)

# Minimum number of columns to consider a pdfplumber result a "real" table.
# Single-column "tables" are almost always false positives from aligned text.
_MIN_TABLE_COLUMNS: int = 2

# Minimum number of rows (including header) to consider a result a table.
_MIN_TABLE_ROWS: int = 2


def extract_tables(source: Path | bytes) -> list[RawTable]:
    """Extract all tables from a PDF using pdfplumber.

    Args:
        source: Path to a PDF file or raw PDF bytes.

    Returns:
        Flat list of ``RawTable`` objects ordered by (page_number, y-position).

    Raises:
        ValueError: If pdfplumber cannot open the file.

    Notes:
        - Very small "tables" (fewer than _MIN_TABLE_COLUMNS columns or
          _MIN_TABLE_ROWS rows) are skipped — they are usually parsing
          artefacts from aligned text or form fields.
        - None values in cells represent empty cells in pdfplumber's output;
          ``RawTable.to_markdown()`` renders them as empty strings.
    """
    try:
        if isinstance(source, bytes):
            import io

            pdf = pdfplumber.open(io.BytesIO(source))
        else:
            pdf = pdfplumber.open(str(source))
    except Exception as exc:
        raise ValueError(f"pdfplumber cannot open PDF: {exc}") from exc

    tables: list[RawTable] = []

    try:
        for page_num, page in enumerate(pdf.pages):
            for table_obj in page.find_tables():
                rows = table_obj.extract()
                if not rows:
                    continue
                # Filter pseudo-tables
                max_cols = max((len(r) for r in rows), default=0)
                if max_cols < _MIN_TABLE_COLUMNS or len(rows) < _MIN_TABLE_ROWS:
                    logger.debug(
                        "table_extractor.skipped_pseudo_table",
                        page=page_num,
                        rows=len(rows),
                        cols=max_cols,
                    )
                    continue

                bbox: tuple[float, float, float, float] = table_obj.bbox
                # block_index approximation: use top y-coordinate position
                block_index = int(bbox[1])

                tables.append(
                    RawTable(
                        page_number=page_num,
                        block_index=block_index,
                        rows=rows,
                        bbox=bbox,
                    )
                )
    finally:
        pdf.close()

    logger.debug(
        "table_extractor.complete",
        total_tables=len(tables),
    )
    return tables


def bbox_overlaps(
    bbox_a: tuple[float, float, float, float],
    bbox_b: tuple[float, float, float, float],
    overlap_threshold: float = 0.5,
) -> bool:
    """Return True if bbox_a and bbox_b overlap by more than ``overlap_threshold``.

    Both bounding boxes are (x0, y0, x1, y1) in the same page coordinate system.

    Used by the orchestrator to suppress PyMuPDF text blocks that fall inside
    a pdfplumber-detected table region (to avoid duplicate content).

    Args:
        bbox_a:             First bounding box.
        bbox_b:             Second bounding box.
        overlap_threshold:  Fraction of bbox_a's area that must be covered by
                            the intersection to count as overlapping.
                            Default 0.5 (majority overlap).

    Returns:
        True if the intersection area is >= ``overlap_threshold`` x area of
        bbox_a; False otherwise.
    """
    ax0, ay0, ax1, ay1 = bbox_a
    bx0, by0, bx1, by1 = bbox_b

    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)

    if ix1 <= ix0 or iy1 <= iy0:
        return False  # No intersection

    intersection_area = (ix1 - ix0) * (iy1 - iy0)
    a_area = (ax1 - ax0) * (ay1 - ay0)
    if a_area == 0:
        return False

    return (intersection_area / a_area) >= overlap_threshold
