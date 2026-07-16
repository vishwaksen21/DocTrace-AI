"""Pass 1 — Structure extraction using PyMuPDF.

Extracts raw text blocks and their layout metadata from a digitally
generated PDF.  This pass is intentionally minimal: it only extracts
raw data; all classification happens in subsequent passes.

Why PyMuPDF as the primary extractor?
--------------------------------------
- 5-10x faster than pdfplumber for text extraction on large documents
- Provides per-span font metadata (size, flags) without additional parsing
- Supports streaming; does not load the entire document into memory at once
- ``page.get_text("dict")`` returns a structured block/line/span hierarchy
  that makes font analysis straightforward

Why NOT pdfplumber here?
    pdfplumber's ``extract_text()`` flattens the layout and loses font
    metadata.  Its value is in table extraction (Pass 3), where its
    grid-detection algorithm is superior to PyMuPDF's.

OCR extensibility:
    After this pass, raw blocks contain ``text`` from extractable PDF text.
    An OCR pass would replace image-type blocks (``block_type == 1``) with
    text produced by an OCR engine.  No other module needs to change.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import fitz  # PyMuPDF

from app.parser.types import RawBlock

logger = logging.getLogger(__name__)

# PyMuPDF font flag bit for bold text.
# See: https://pymupdf.readthedocs.io/en/latest/font.html
_BOLD_FLAG: int = 1 << 4  # bit 4 (16) → bold


def extract_blocks(source: Path | bytes) -> list[RawBlock]:
    """Extract raw text blocks from a PDF file or bytes buffer.

    Opens the PDF using PyMuPDF and iterates over every text block on
    every page, collecting layout metadata (font size, bold, bbox).

    Args:
        source: Either a ``pathlib.Path`` to a PDF file or raw PDF bytes.
            Passing bytes avoids a temporary file when the PDF is received
            from an HTTP upload and has not been flushed to disk yet.

    Returns:
        A flat list of ``RawBlock`` objects ordered by (page_number, block_index).
        Image blocks (``block_type == 1``) are included with empty text —
        OCR can fill them in a later pass.

    Raises:
        ValueError: If the PDF cannot be opened (e.g., corrupt, encrypted).
        RuntimeError: If PyMuPDF raises an unexpected internal error.

    Notes:
        - Pages with no extractable text blocks return zero RawBlocks.
        - Blocks with only whitespace are kept (they carry position information
          that may matter for layout analysis) but are filtered by later passes.
    """
    try:
        if isinstance(source, bytes):
            doc = fitz.open(stream=io.BytesIO(source), filetype="pdf")
        else:
            doc = fitz.open(str(source))
    except fitz.FileDataError as exc:
        raise ValueError(f"Cannot open PDF: {exc}") from exc

    blocks: list[RawBlock] = []

    try:
        for page_num, page in enumerate(doc):
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for block in page_dict.get("blocks", []):
                block_type: int = block.get("type", 0)
                bbox: tuple[float, float, float, float] = tuple(block.get("bbox", (0, 0, 0, 0)))  # type: ignore[assignment]

                if block_type == 1:
                    # Image block — no text; OCR can fill this later.
                    blocks.append(
                        RawBlock(
                            page_number=page_num,
                            block_index=block.get("number", len(blocks)),
                            text="",
                            font_size=0.0,
                            is_bold=False,
                            is_italic=False,
                            bbox=bbox,
                            block_type=1,
                        )
                    )
                    continue

                # Text block: aggregate font metadata across all spans.
                dominant_size, is_bold, is_italic = _dominant_font_props(block)
                raw_text = _block_text(block)

                blocks.append(
                    RawBlock(
                        page_number=page_num,
                        block_index=block.get("number", len(blocks)),
                        text=raw_text,
                        font_size=dominant_size,
                        is_bold=is_bold,
                        is_italic=is_italic,
                        bbox=bbox,
                        block_type=0,
                    )
                )
    finally:
        doc.close()

    logger.debug(
        "structure_extractor.extracted",
        total_blocks=len(blocks),
        source=str(source) if isinstance(source, Path) else "<bytes>",
    )
    return blocks


# ── Private helpers ───────────────────────────────────────────────────────────


def _block_text(block: dict) -> str:  # type: ignore[type-arg]
    """Concatenate all span texts within a block into a single string.

    Lines within a block are joined with ``\\n``; spans within a line
    are concatenated directly (PyMuPDF preserves spacing in span text).
    """
    lines: list[str] = []
    for line in block.get("lines", []):
        span_text = "".join(span.get("text", "") for span in line.get("spans", []))
        lines.append(span_text)
    return "\n".join(lines)


def _dominant_font_props(block: dict) -> tuple[float, bool, bool]:  # type: ignore[type-arg]
    """Return (dominant_font_size, is_bold, is_italic) for the block.

    Dominance is determined by total character count: the font that
    covers the most characters wins.  This handles mixed-format blocks
    (e.g., a heading with a bold prefix and a normal-weight suffix)
    correctly — the longer portion governs the classification.

    Returns:
        A 3-tuple: (font_size, is_bold, is_italic).
    """
    size_char_count: dict[float, int] = {}
    bold_char_count = 0
    italic_char_count = 0
    total_chars = 0

    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "")
            n = len(text)
            total_chars += n
            size = float(span.get("size", 0.0))
            flags = int(span.get("flags", 0))
            size_char_count[size] = size_char_count.get(size, 0) + n
            if flags & _BOLD_FLAG:
                bold_char_count += n
            # PyMuPDF italic flag is bit 1 (2)
            if flags & 0b10:
                italic_char_count += n

    if not size_char_count:
        return 0.0, False, False

    dominant_size = max(size_char_count, key=lambda s: size_char_count[s])
    half = total_chars / 2
    return dominant_size, bold_char_count > half, italic_char_count > half
