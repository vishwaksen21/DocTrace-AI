"""Unit tests for SqlAlchemyDocumentRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Document
from app.repositories.document import SqlAlchemyDocumentRepository


@pytest.mark.anyio
class TestSqlAlchemyDocumentRepository:
    """Tests for the SqlAlchemyDocumentRepository."""

    async def test_create_and_get_by_id(self, test_session: AsyncSession) -> None:
        repo = SqlAlchemyDocumentRepository(test_session)
        doc = Document(
            id=uuid4(),
            title="Ingestion Guide",
            original_filename="ingest.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )

        saved = await repo.create(doc)
        assert saved.id == doc.id
        assert saved.title == "Ingestion Guide"
        assert isinstance(saved.created_at, datetime)
        assert isinstance(saved.updated_at, datetime)

        fetched = await repo.get_by_id(doc.id)
        assert fetched is not None
        assert fetched.id == doc.id
        assert fetched.title == "Ingestion Guide"

    async def test_get_by_id_missing_returns_none(self, test_session: AsyncSession) -> None:
        repo = SqlAlchemyDocumentRepository(test_session)
        assert await repo.get_by_id(uuid4()) is None

    async def test_list_paginated_and_count(self, test_session: AsyncSession) -> None:
        repo = SqlAlchemyDocumentRepository(test_session)
        assert await repo.count() == 0

        doc1 = Document(
            id=uuid4(),
            title="Doc 1",
            original_filename="1.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        doc2 = Document(
            id=uuid4(),
            title="Doc 2",
            original_filename="2.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )

        await repo.create(doc1)
        await repo.create(doc2)

        assert await repo.count() == 2

        # Page 1, limit 1
        items1, total = await repo.list_paginated(offset=0, limit=1)
        assert total == 2
        assert len(items1) == 1

        # Page 2, limit 1
        items2, total = await repo.list_paginated(offset=1, limit=1)
        assert total == 2
        assert len(items2) == 1

        assert {items1[0].id, items2[0].id} == {doc1.id, doc2.id}

    async def test_exists_and_delete(self, test_session: AsyncSession) -> None:
        repo = SqlAlchemyDocumentRepository(test_session)
        doc_id = uuid4()
        doc = Document(
            id=doc_id,
            title="Delete Me",
            original_filename="del.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )

        assert await repo.exists(doc_id) is False
        await repo.create(doc)
        assert await repo.exists(doc_id) is True

        await repo.delete(doc_id)
        assert await repo.exists(doc_id) is False
        assert await repo.get_by_id(doc_id) is None
