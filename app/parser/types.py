"""Intermediate data types shared across parser passes.

All types here are plain Python dataclasses with no framework dependencies.
They represent the pipeline's internal state between passes and the final
output that the service layer consumes.

Why separate from domain entities?
    ``app.domain.entities.Node`` is the *persisted* domain object with a
    UUID, version_id, and created_at timestamp.  ``ParsedNode`` is the
    *in-flight* representation produced by the parser — it has no ID yet
    and contains additional parser-specific fields (raw_block_index,
    classification_confidence) that are not persisted.

    The document service maps ``ParsedNode`` → ``Node`` (domain entity)
    after assigning UUIDs and timestamps.  This keeps the parser output
    clean and independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import NodeType


@dataclass
class RawBlock:
    """A raw text block as extracted from the PDF by PyMuPDF.

    Represents one contiguous span of text on a single page, with its
    layout metadata.  Multiple RawBlocks are combined into a single
    ParsedNode when they belong to the same structural unit.

    Attributes:
        page_number:  0-based page index.
        block_index:  0-based block ordering within the page.
        text:         Raw text content (may contain trailing whitespace).
        font_size:    Dominant font size in the block (points).
        is_bold:      True if the dominant font span is bold.
        is_italic:    True if the dominant font span is italic.
        bbox:         Bounding box as (x0, y0, x1, y1) in page coordinates.
        block_type:   PyMuPDF block type: 0 = text, 1 = image.
    """

    page_number: int
    block_index: int
    text: str
    font_size: float
    is_bold: bool
    is_italic: bool
    bbox: tuple[float, float, float, float]
    block_type: int = 0  # 0 = text; 1 = image


@dataclass
class RawTable:
    """A raw table as extracted by pdfplumber.

    Attributes:
        page_number:  0-based page index.
        block_index:  Approximate position relative to text blocks on the page.
        rows:         List of rows; each row is a list of cell strings (may be None).
        bbox:         Bounding box as (x0, y0, x1, y1).
    """

    page_number: int
    block_index: int
    rows: list[list[str | None]]
    bbox: tuple[float, float, float, float]

    def to_markdown(self) -> str:
        """Render the table as a Markdown table string.

        Empty / None cells are rendered as empty strings.  The header
        separator row (``| --- |``) is always inserted after the first row
        so that the output is valid Markdown regardless of the actual
        content.

        Returns:
            A multi-line Markdown table string, e.g.::

                | Col A | Col B |
                | --- | --- |
                | v1   | v2   |

        Raises:
            ValueError: If the table has no rows.
        """
        if not self.rows:
            raise ValueError("Cannot render an empty table as Markdown.")

        def _cell(c: str | None) -> str:
            return (c or "").strip().replace("|", "\\|")

        lines: list[str] = []
        header = self.rows[0]
        lines.append("| " + " | ".join(_cell(c) for c in header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in self.rows[1:]:
            lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
        return "\n".join(lines)


@dataclass
class ParsedNode:
    """An intermediate node produced by the parser pipeline.

    This is the output of the hierarchy builder (Pass 5) and the input
    to the document service layer.  The service layer assigns UUIDs,
    version_id, and created_at before persisting to the database.

    Attributes:
        node_type:                Structural type of this node.
        content:                  Text content.  Tables are in Markdown format.
        content_hash:             SHA-256 hex digest of normalised content.
        position_index:           Global 0-based ordering within this parse run.
        path:                     Materialized path (e.g. ``"0.2.1"``).
        heading_level:            1-6 for HEADING nodes; None otherwise.
        parent_position_index:    ``position_index`` of the parent node;
                                  None for root nodes.
        classification_confidence: Heuristic confidence (0.0-1.0) for headings.
                                  Always 1.0 for non-heading nodes.
        raw_metadata:             Arbitrary parser-internal metadata for
                                  debugging (page_number, block_index, bbox…).
                                  Not persisted to the database.
    """

    node_type: NodeType
    content: str
    content_hash: str
    position_index: int
    path: str
    heading_level: int | None = None
    parent_position_index: int | None = None
    classification_confidence: float = 1.0
    raw_metadata: dict[str, Any] = field(default_factory=dict)
