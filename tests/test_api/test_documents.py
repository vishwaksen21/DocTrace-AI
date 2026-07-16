"""Integration tests for Document and Version API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
class TestDocumentAPI:
    """API tests for the /documents resource."""

    async def test_upload_document_success(self, client: AsyncClient) -> None:
        # Mock PDF parsing to prevent actual PDF parsing attempts
        with patch("app.parser.pdf_parser.parse_pdf", AsyncMock(return_value=[])):
            response = await client.post(
                "/api/v1/documents",
                data={"title": "Audit Protocol"},
                files={"file": ("audit.pdf", b"pdf-data", "application/pdf")},
            )

            assert response.status_code == 201
            data = response.json()
            assert "document" in data
            assert "version" in data
            assert data["document"]["title"] == "Audit Protocol"
            assert data["version"]["version_number"] == 1
            assert data["version"]["status"] == "processing"

    async def test_get_document_success(self, client: AsyncClient) -> None:
        # 1. Create document first
        with patch("app.parser.pdf_parser.parse_pdf", AsyncMock(return_value=[])):
            res_create = await client.post(
                "/api/v1/documents",
                data={"title": "Audit Protocol"},
                files={"file": ("audit.pdf", b"pdf-data", "application/pdf")},
            )
            doc_id = res_create.json()["document"]["id"]

            # 2. Get document by ID
            response = await client.get(f"/api/v1/documents/{doc_id}")
            assert response.status_code == 200
            assert response.json()["title"] == "Audit Protocol"

    async def test_get_document_not_found(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/v1/documents/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["error"] == "NotFound"

    async def test_list_documents(self, client: AsyncClient) -> None:
        with patch("app.parser.pdf_parser.parse_pdf", AsyncMock(return_value=[])):
            await client.post(
                "/api/v1/documents",
                data={"title": "Doc A"},
                files={"file": ("a.pdf", b"pdf-data", "application/pdf")},
            )

        response = await client.get("/api/v1/documents?offset=0&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_upload_version_success(self, client: AsyncClient) -> None:
        with patch("app.parser.pdf_parser.parse_pdf", AsyncMock(return_value=[])):
            # 1. Upload original document
            res_create = await client.post(
                "/api/v1/documents",
                data={"title": "Specification"},
                files={"file": ("spec.pdf", b"v1-bytes", "application/pdf")},
            )
            doc_id = res_create.json()["document"]["id"]

            # 2. Upload version 2
            response = await client.post(
                f"/api/v1/documents/{doc_id}/versions",
                files={"file": ("spec_v2.pdf", b"v2-bytes", "application/pdf")},
            )
            assert response.status_code == 202
            data = response.json()
            assert data["version_number"] == 2
            assert data["status"] == "processing"

    async def test_list_versions(self, client: AsyncClient) -> None:
        with patch("app.parser.pdf_parser.parse_pdf", AsyncMock(return_value=[])):
            # 1. Create document
            res_create = await client.post(
                "/api/v1/documents",
                data={"title": "Release Notes"},
                files={"file": ("notes.pdf", b"v1", "application/pdf")},
            )
            doc_id = res_create.json()["document"]["id"]

            # 2. List versions
            response = await client.get(f"/api/v1/documents/{doc_id}/versions")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert len(data["items"]) == 1
            assert data["items"][0]["version_number"] == 1
