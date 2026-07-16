# ADR 0005: PDF Parsing Pipeline — PyMuPDF + Hierarchy Builder

## Status
Accepted

## Context
Need to extract structured content from PDFs:
- Text with font metadata (size, weight, font)
- Headings (hierarchy levels)
- Lists (ordered/unordered)
- Tables
- Position information for diff anchoring

## Decision
**Primary: PyMuPDF (fitz)** — fast, preserves structure, exposes font metadata.
**Secondary: pdfplumber** — better table extraction, used only for tables.

### Pipeline (`app/parser/`)
```
PDF bytes
    │
    ▼
┌─────────────────────────────────────┐
│ pdf_parser.py (PyMuPDF)             │
│ - Extract pages → blocks → lines    │
│ - Font size, flags, bbox, text      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ heading_detector.py                 │
│ - Heuristics: font size, bold,      │
│   numbering, position               │
│ - Output: heading level (1-6)       │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ list_detector.py                    │
│ - Bullet/number patterns            │
│ - Indentation levels                │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ structure_extractor.py              │
│ - Merge lines → paragraphs          │
│ - Classify: heading/paragraph/list/ │
│   table/code                        │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ hierarchy_builder.py                │
│ - Build tree from heading levels    │
│ - Assign parent_id, path,           │
│   position_index                    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ content_hasher.py                   │
│ - SHA-256 of normalized text        │
│ - 64-char hex for Node.content_hash │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ table_extractor.py (pdfplumber)     │
│ - Extract tables → markdown         │
│ - Associate with nearest heading    │
└─────────────────────────────────────┘
```

### Node Output (`app/domain/entities.py`)
```python
@dataclass(frozen=True)
class Node:
    id: UUID
    version_id: UUID
    type: NodeType          # HEADING, PARAGRAPH, LIST_ITEM, TABLE, CODE
    content: str
    content_hash: str       # SHA-256, 64 chars
    heading_level: int | None  # 1-6 for HEADING
    parent_id: UUID | None
    path: str               # "1.2.3" — heading hierarchy path
    position_index: int     # Global order in document
    bbox: BoundingBox | None
    metadata: dict          # font_size, is_bold, list_marker, etc.
```

### Heading Detection Heuristics
```python
# heading_detector.py
def detect_heading_level(line: TextLine, context: PageContext) -> int | None:
    # 1. Explicit numbering: "1.2.3 Title"
    if match := NUMBERING_PATTERN.match(line.text):
        return len(match.group(1).split("."))

    # 2. Font size relative to body
    if line.font_size > context.body_font_size * 1.3:
        return 1
    elif line.font_size > context.body_font_size * 1.15:
        return 2
    elif line.font_size > context.body_font_size * 1.05:
        return 3

    # 3. Bold + larger
    if line.is_bold and line.font_size > context.body_font_size:
        return min(3, estimate_by_size(line.font_size))

    return None
```

### Content Hashing
```python
# content_hasher.py
def compute_content_hash(text: str) -> str:
    # Normalize: collapse whitespace, strip, lowercase
    normalized = " ".join(text.split()).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()
```

### Table Extraction
- Only runs if `pdfplumber` detects tables on page
- Converts to Markdown pipe format
- Creates `Node(type=TABLE, content=markdown_table)`
- Links to nearest preceding heading via `parent_id`

## Consequences
### Positive
- PyMuPDF: ~10x faster than pdfplumber for text
- Font metadata enables reliable heading detection
- Position index enables version diff anchoring
- Modular pipeline — each step testable in isolation

### Negative
- Two PDF libraries (size ~50MB)
- Heuristics may misclassify unusual layouts
- Tables only extracted when pdfplumber finds them
- No OCR (scanned PDFs unsupported)

## Configuration
```python
# app/core/constants.py
DEFAULT_BODY_FONT_SIZE = 11.0
HEADING_SIZE_RATIOS = {1: 1.3, 2: 1.15, 3: 1.05}
MIN_HEADING_LENGTH = 3
MAX_HEADING_LENGTH = 200
```

## Testing
- 18 parser unit tests (heading, list, hierarchy, hash)
- 4 PDF fixture files (simple, nested headings, tables, lists)
- Golden master tests: parse → serialize → compare JSON
- Performance: <2s for 50-page PDF

## Future Work
- OCR fallback (Tesseract) for scanned PDFs
- LayoutLM for semantic structure detection
- Formula/diagram extraction