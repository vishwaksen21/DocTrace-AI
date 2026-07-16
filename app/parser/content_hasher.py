"""SHA-256 content hasher for deterministic node change detection.

This module is the foundation of the versioning diff algorithm.
Every node's ``content_hash`` is computed here; the diff engine
then performs O(1) change detection by comparing hashes.

Normalisation contract
----------------------
The hash is computed over *normalised* content rather than raw content.
Normalisation removes superficial formatting differences that do not
represent meaningful content changes:

1. Unicode normalisation (NFC) — resolves composed vs. decomposed forms
2. Whitespace collapse — consecutive whitespace (space, tab, NBSP) → single space
3. Line ending normalisation — ``\\r\\n`` and ``\\r`` → ``\\n``
4. Leading/trailing whitespace strip — trim the final string

This contract is **immutable once nodes are in the database**.  Changing
normalisation rules would invalidate all stored hashes and produce false
diffs for every re-upload.  Any future change must be introduced as a
new hash algorithm with a migration.

Usage::

    from app.parser.content_hasher import compute_hash, normalise_content

    raw = "  Hello\\r\\nWorld  "
    normalised = normalise_content(raw)  # "Hello\\nWorld"
    h = compute_hash(raw)               # SHA-256 hex of normalised form
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from app.core.constants import CONTENT_HASH_ALGORITHM, CONTENT_HASH_HEX_LENGTH

# Compiled once at module load; matching is O(n) per call.
_WHITESPACE_RE = re.compile(r"[ \t\u00a0\u2003]+")  # space / tab / NBSP / EM SPACE
_LINE_ENDING_RE = re.compile(r"\r\n|\r")


def normalise_content(text: str) -> str:
    """Return the canonical, normalised form of ``text``.

    Transformations applied in order:
        1. NFC Unicode normalisation
        2. Line-ending normalisation (``\\r\\n``, ``\\r`` → ``\\n``)
        3. Horizontal whitespace collapse within each line
        4. Strip leading/trailing whitespace from the result

    This function is **idempotent**: calling it twice on the same input
    produces the same output as calling it once.

    Args:
        text: Raw content extracted from the PDF parser.

    Returns:
        Normalised string.

    Examples:
        >>> normalise_content("  Hello   World  ")
        'Hello World'
        >>> normalise_content("Line1\\r\\nLine2")
        'Line1\\nLine2'
        >>> normalise_content("café")  # NFC: é as composed character
        'café'
    """
    # Step 1: NFC normalisation
    text = unicodedata.normalize("NFC", text)
    # Step 2: normalise line endings
    text = _LINE_ENDING_RE.sub("\n", text)
    # Step 3: collapse horizontal whitespace within each line
    lines = [_WHITESPACE_RE.sub(" ", line) for line in text.split("\n")]
    # Step 4: strip each line, then strip the whole result
    text = "\n".join(line.strip() for line in lines).strip()
    return text


def compute_hash(text: str) -> str:
    """Compute the SHA-256 hex digest of the normalised content.

    The hash is always computed over the *normalised* form of ``text``
    (see :func:`normalise_content`).  Passing already-normalised text
    produces the same result due to idempotence.

    Args:
        text: Raw or normalised content to hash.

    Returns:
        64-character lowercase hex string (SHA-256 digest).

    Raises:
        ValueError: If the resulting digest is not 64 characters.
            This should never happen in practice; the check guards
            against algorithm substitution bugs.

    Examples:
        >>> h = compute_hash("Hello World")
        >>> len(h)
        64
        >>> compute_hash("  Hello   World  ") == compute_hash("Hello World")
        True
    """
    normalised = normalise_content(text)
    digest = hashlib.new(CONTENT_HASH_ALGORITHM, normalised.encode("utf-8")).hexdigest()
    if len(digest) != CONTENT_HASH_HEX_LENGTH:  # pragma: no cover
        raise ValueError(
            f"Hash algorithm '{CONTENT_HASH_ALGORITHM}' produced a "
            f"{len(digest)}-character digest; expected {CONTENT_HASH_HEX_LENGTH}."
        )
    return digest
