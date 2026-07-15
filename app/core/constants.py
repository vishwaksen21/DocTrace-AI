"""Application-wide constants.

This module contains values that are fixed at compile time and do not
depend on runtime configuration.  For values that may change across
environments or deployments, use ``app.core.config`` instead.

Naming convention:
    SCREAMING_SNAKE_CASE for all constants, grouped by concern.
"""

from __future__ import annotations

# ── API ───────────────────────────────────────────────────────────────────────

API_V1_PREFIX: str = "/api/v1"

#: Header name used to propagate per-request correlation IDs
HEADER_REQUEST_ID: str = "X-Request-ID"

# ── Content hashing ───────────────────────────────────────────────────────────

#: Algorithm used to compute deterministic node content hashes
CONTENT_HASH_ALGORITHM: str = "sha256"

#: Expected length of a SHA-256 hex digest (32 bytes → 64 hex characters)
CONTENT_HASH_HEX_LENGTH: int = 64

# ── Version diffing ───────────────────────────────────────────────────────────

#: ±N positions within which a same-hash node is considered "in-place"
#: rather than "moved" during version comparison.
DIFF_POSITION_TOLERANCE: int = 3

# ── PDF parsing ───────────────────────────────────────────────────────────────

#: Minimum heuristic confidence (0-1) to classify a text block as a heading.
#: Blocks below this threshold are recorded as paragraphs to avoid silent loss.
HEADING_MIN_CONFIDENCE: float = 0.8

#: HTML / Markdown heading depth limit (H1 … H6)
MAX_HEADING_DEPTH: int = 6

# ── MongoDB collections ───────────────────────────────────────────────────────

MONGO_COLLECTION_GENERATIONS: str = "generation_results"

# ── LLM ──────────────────────────────────────────────────────────────────────

#: Request body fragment that instructs compatible models to return JSON
LLM_JSON_RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}

#: Default temperature for QA test-case generation.
#: Low value → deterministic, consistent structure.
LLM_DEFAULT_TEMPERATURE: float = 0.1

# ── Pagination ────────────────────────────────────────────────────────────────

#: Used as a fallback when settings are not yet available (e.g., in tests)
FALLBACK_PAGE_SIZE: int = 20
