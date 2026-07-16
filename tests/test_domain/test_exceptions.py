"""Tests for app/domain/exceptions.py."""

from __future__ import annotations

import uuid

import pytest

from app.domain.exceptions import (
    BusinessValidationError,
    ConflictError,
    CrossVersionSelectionError,
    DocumentNotFoundError,
    DomainError,
    DuplicateVersionError,
    EmptySelectionError,
    GenerationNotFoundError,
    NodeNotFoundError,
    NotFoundError,
    PDFParsingError,
    ProcessingError,
    SelectionNotFoundError,
    VersionDiffError,
    VersionNotFoundError,
    VersionNotReadyError,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_DOC_ID = uuid.uuid4()
_VER_ID = uuid.uuid4()
_NODE_ID = uuid.uuid4()
_SEL_ID = uuid.uuid4()


# ── Inheritance ───────────────────────────────────────────────────────────────


class TestInheritanceHierarchy:
    """All domain exceptions must follow the documented taxonomy."""

    def test_not_found_inherits_domain_error(self) -> None:
        exc = DocumentNotFoundError(_DOC_ID)
        assert isinstance(exc, NotFoundError)
        assert isinstance(exc, DomainError)
        assert isinstance(exc, Exception)

    def test_conflict_inherits_domain_error(self) -> None:
        exc = DuplicateVersionError(_DOC_ID, 3)
        assert isinstance(exc, ConflictError)
        assert isinstance(exc, DomainError)

    def test_business_validation_inherits_domain_error(self) -> None:
        exc = EmptySelectionError()
        assert isinstance(exc, BusinessValidationError)
        assert isinstance(exc, DomainError)

    def test_processing_inherits_domain_error(self) -> None:
        exc = PDFParsingError("test.pdf", "corrupt header")
        assert isinstance(exc, ProcessingError)
        assert isinstance(exc, DomainError)


# ── Not Found ─────────────────────────────────────────────────────────────────


class TestNotFoundExceptions:
    """Not-found exceptions carry typed IDs and self-describing messages."""

    def test_document_not_found_message_contains_id(self) -> None:
        exc = DocumentNotFoundError(_DOC_ID)
        assert str(_DOC_ID) in str(exc)
        assert exc.document_id == _DOC_ID

    def test_document_not_found_details(self) -> None:
        exc = DocumentNotFoundError(_DOC_ID)
        assert exc.details["document_id"] == str(_DOC_ID)

    def test_version_not_found_carries_version_id(self) -> None:
        exc = VersionNotFoundError(_VER_ID)
        assert exc.version_id == _VER_ID
        assert str(_VER_ID) in exc.message

    def test_node_not_found_carries_node_id(self) -> None:
        exc = NodeNotFoundError(_NODE_ID)
        assert exc.node_id == _NODE_ID

    def test_selection_not_found_carries_selection_id(self) -> None:
        exc = SelectionNotFoundError(_SEL_ID)
        assert exc.selection_id == _SEL_ID

    def test_generation_not_found_carries_str_id(self) -> None:
        exc = GenerationNotFoundError("64b0d0f4a3b2c1d0e5f6a7b8")
        assert exc.generation_id == "64b0d0f4a3b2c1d0e5f6a7b8"

    def test_all_not_found_are_catchable_as_domain_error(self) -> None:
        errors = [
            DocumentNotFoundError(_DOC_ID),
            VersionNotFoundError(_VER_ID),
            NodeNotFoundError(_NODE_ID),
            SelectionNotFoundError(_SEL_ID),
        ]
        for e in errors:
            with pytest.raises(DomainError):
                raise e


# ── Conflict ──────────────────────────────────────────────────────────────────


class TestConflictExceptions:
    def test_duplicate_version_carries_doc_id_and_number(self) -> None:
        exc = DuplicateVersionError(_DOC_ID, 5)
        assert exc.document_id == _DOC_ID
        assert exc.version_number == 5
        assert "5" in exc.message
        assert str(_DOC_ID) in exc.message

    def test_details_contain_both_fields(self) -> None:
        exc = DuplicateVersionError(_DOC_ID, 2)
        assert exc.details["version_number"] == 2
        assert exc.details["document_id"] == str(_DOC_ID)


# ── Business Validation ───────────────────────────────────────────────────────


class TestBusinessValidationExceptions:
    def test_empty_selection_has_helpful_message(self) -> None:
        exc = EmptySelectionError()
        assert "at least one node" in exc.message.lower()

    def test_cross_version_selection_reports_count(self) -> None:
        ids = {uuid.uuid4(), uuid.uuid4(), uuid.uuid4()}
        exc = CrossVersionSelectionError(ids)
        assert "3" in exc.message
        assert exc.version_ids == ids

    def test_cross_version_details_are_strings(self) -> None:
        ids = {uuid.uuid4()}
        exc = CrossVersionSelectionError(ids)
        # details["version_ids"] must be JSON-serializable strings, not UUIDs
        for v in exc.details["version_ids"]:
            assert isinstance(v, str)

    def test_version_not_ready_carries_status(self) -> None:
        exc = VersionNotReadyError(_VER_ID, "processing")
        assert exc.version_id == _VER_ID
        assert exc.current_status == "processing"
        assert "processing" in exc.message


# ── Processing Errors ─────────────────────────────────────────────────────────


class TestProcessingErrors:
    def test_pdf_parsing_error_carries_filename_and_reason(self) -> None:
        exc = PDFParsingError("report.pdf", "encrypted PDF")
        assert exc.filename == "report.pdf"
        assert exc.reason == "encrypted PDF"
        assert "report.pdf" in exc.message

    def test_version_diff_error_carries_both_version_ids(self) -> None:
        id_a, id_b = uuid.uuid4(), uuid.uuid4()
        exc = VersionDiffError(id_a, id_b, "node count mismatch")
        assert exc.version_id_a == id_a
        assert exc.version_id_b == id_b
        assert "node count mismatch" in exc.message

    def test_domain_error_default_details_is_empty_dict(self) -> None:
        exc = DomainError("generic error")
        assert exc.details == {}

    def test_domain_error_custom_details_are_preserved(self) -> None:
        exc = DomainError("msg", details={"key": "value"})
        assert exc.details["key"] == "value"
