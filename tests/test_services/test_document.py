"""Unit tests for DocumentService."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import SqlAlchemyDocumentRepository, SqlAlchemyVersionRepository
from app.services.document import DocumentService


@pytest.mark.anyio
class TestDocumentService:
    """Tests for the DocumentService class."""

    async def test_create_and_get_document(self, service_session: AsyncSession) -> None:
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        service = DocumentService(doc_repo, ver_repo)

        doc = await service.create_document(title="User Guide", original_filename="guide.pdf")
        assert doc.id is not None
        assert doc.title == "User Guide"

        # Fetch it back
        fetched = await service.get_document(doc.id)
        assert fetched is not None
        assert fetched.id == doc.id
        assert fetched.title == "User Guide"

    async def test_get_document_missing_returns_none(self, service_session: AsyncSession) -> None:
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        service = DocumentService(doc_repo, ver_repo)

        assert await service.get_document(uuid4()) is None

    async def test_list_documents(self, service_session: AsyncSession) -> None:
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        service = DocumentService(doc_repo, ver_repo)

        doc1 = await service.create_document(title="Doc 1", original_filename="1.pdf")
        doc2 = await service.create_document(title="Doc 2", original_filename="2.pdf")

        items, total = await service.list_documents(offset=0, limit=10)
        assert total == 2
        assert len(items) == 2
        assert {items[0].id, items[1].id} == {doc1.id, doc2.id}

    async def test_delete_document(self, service_session: AsyncSession) -> None:
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        service = DocumentService(doc_repo, ver_repo)

        doc = await service.create_document(title="Delete Me", original_filename="del.pdf")
        assert await service.get_document(doc.id) is not None

        await service.delete_document(doc.id)
        assert await service.get_document(doc.id) is None
