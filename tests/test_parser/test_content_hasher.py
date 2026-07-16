"""Tests for app/parser/content_hasher.py."""

from __future__ import annotations

import hashlib

from app.parser.content_hasher import compute_hash, normalise_content


class TestNormaliseContent:
    """normalise_content() must be deterministic and idempotent."""

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert normalise_content("  hello  ") == "hello"

    def test_collapses_multiple_spaces(self) -> None:
        assert normalise_content("hello   world") == "hello world"

    def test_collapses_tabs(self) -> None:
        assert normalise_content("hello\t\tworld") == "hello world"

    def test_collapses_nbsp(self) -> None:
        # U+00A0 = non-breaking space
        assert normalise_content("hello\u00a0world") == "hello world"

    def test_normalises_crlf_to_lf(self) -> None:
        assert normalise_content("line1\r\nline2") == "line1\nline2"

    def test_normalises_cr_to_lf(self) -> None:
        assert normalise_content("line1\rline2") == "line1\nline2"

    def test_nfc_normalisation(self) -> None:
        # "é" can be NFD (e + combining accent) or NFC (precomposed é)
        nfd = "\u0065\u0301"  # e + combining acute accent
        nfc = "\u00e9"  # é precomposed
        assert normalise_content(nfd) == nfc

    def test_idempotent(self) -> None:
        raw = "  Hello   World\r\n  Foo  "
        once = normalise_content(raw)
        twice = normalise_content(once)
        assert once == twice

    def test_empty_string(self) -> None:
        assert normalise_content("") == ""

    def test_only_whitespace_becomes_empty(self) -> None:
        assert normalise_content("   \t  \r\n  ") == ""

    def test_multiline_preserves_line_boundaries(self) -> None:
        result = normalise_content("line1\nline2\nline3")
        assert result == "line1\nline2\nline3"

    def test_inline_whitespace_does_not_collapse_across_lines(self) -> None:
        """Spaces on different lines should NOT be merged across the newline."""
        result = normalise_content("hello  \n  world")
        assert result == "hello\nworld"


class TestComputeHash:
    """compute_hash() must produce consistent 64-char SHA-256 digests."""

    def test_returns_64_char_hex_string(self) -> None:
        h = compute_hash("Hello World")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_identical_inputs_produce_identical_hashes(self) -> None:
        assert compute_hash("Hello World") == compute_hash("Hello World")

    def test_different_inputs_produce_different_hashes(self) -> None:
        assert compute_hash("Hello World") != compute_hash("Hello World!")

    def test_hash_is_over_normalised_content(self) -> None:
        """Two inputs that normalise to the same string must have the same hash."""
        raw1 = "  Hello   World  "
        raw2 = "Hello World"
        assert compute_hash(raw1) == compute_hash(raw2)

    def test_crlf_and_lf_produce_same_hash(self) -> None:
        assert compute_hash("line1\r\nline2") == compute_hash("line1\nline2")

    def test_matches_manual_sha256(self) -> None:
        text = "DocTrace AI"
        normalised = "DocTrace AI"  # already normalised
        expected = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
        assert compute_hash(text) == expected

    def test_empty_string_hash(self) -> None:
        # SHA-256 of "" is well-known; ensure we don't crash.
        h = compute_hash("")
        assert len(h) == 64

    def test_unicode_input(self) -> None:
        # Non-ASCII content should not crash
        h = compute_hash("Ünïcödé têxt")
        assert len(h) == 64

    def test_whitespace_only_hash_equals_empty_string_hash(self) -> None:
        """Whitespace-only and empty string both normalise to '' → same hash."""
        assert compute_hash("   ") == compute_hash("")
