"""Unit tests for SqlAlchemyVersionRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Document, Version
from app.domain.enums import VersionStatus
from app.repositories.document import SqlAlchemyDocumentRepository
from app.repositories.version import SqlAlchemyVersionRepository


@pytest.mark.anyio
class TestSqlAlchemyVersionRepository:
    """Tests for the SqlAlchemyVersionRepository."""

    async def _setup_document(self, session: AsyncSession) -> Document:
        doc_repo = SqlAlchemyDocumentRepository(session)
        doc = Document(
            id=uuid4(),
            title="Parent Doc",
            original_filename="parent.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        return await doc_repo.create(doc)

    async def test_create_and_get_by_id(self, test_session: AsyncSession) -> None:
        doc = await self._setup_document(test_session)
        repo = SqlAlchemyVersionRepository(test_session)

        version_id = uuid4()
        ver = Version(
            id=version_id,
            document_id=doc.id,
            version_number=1,
            upload_filename="upload_v1.pdf",
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )

        saved = await repo.create(ver)
        assert saved.id == version_id
        assert saved.document_id == doc.id
        assert saved.version_number == 1
        assert saved.status == VersionStatus.PROCESSING

        fetched = await repo.get_by_id(version_id)
        assert fetched is not None
        assert fetched.id == version_id
        assert fetched.version_number == 1

    async def test_get_by_id_missing_returns_none(self, test_session: AsyncSession) -> None:
        repo = SqlAlchemyVersionRepository(test_session)
        assert await repo.get_by_id(uuid4()) is None

    async def test_list_for_document(self, test_session: AsyncSession) -> None:
        doc = await self._setup_document(test_session)
        repo = SqlAlchemyVersionRepository(test_session)

        v1 = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        v2 = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=2,
            upload_filename="v2.pdf",
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )

        await repo.create(v1)
        await repo.create(v2)

        items, total = await repo.list_for_document(doc.id, offset=0, limit=1)
        assert total == 2
        assert len(items) == 1
        assert items[0].version_number == 1

        items, total = await repo.list_for_document(doc.id, offset=1, limit=10)
        assert total == 2
        assert len(items) == 1
        assert items[0].version_number == 2

    async def test_get_latest_and_previous_version(self, test_session: AsyncSession) -> None:
        doc = await self._setup_document(test_session)
        repo = SqlAlchemyVersionRepository(test_session)

        assert await repo.get_latest_for_document(doc.id) is None

        v1 = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        v2 = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=2,
            upload_filename="v2.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )

        await repo.create(v1)
        await repo.create(v2)

        latest = await repo.get_latest_for_document(doc.id)
        assert latest is not None
        assert latest.version_number == 2

        prev = await repo.get_previous_version(doc.id, version_number=2)
        assert prev is not None
        assert prev.version_number == 1

        prev_missing = await repo.get_previous_version(doc.id, version_number=1)
        assert prev_missing is None

    async def test_get_next_version_number(self, test_session: AsyncSession) -> None:
        doc = await self._setup_document(test_session)
        repo = SqlAlchemyVersionRepository(test_session)

        assert await repo.get_next_version_number(doc.id) == 1

        v1 = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await repo.create(v1)

        assert await repo.get_next_version_number(doc.id) == 2

    async def test_update_status(self, test_session: AsyncSession) -> None:
        doc = await self._setup_document(test_session)
        repo = SqlAlchemyVersionRepository(test_session)

        v_id = uuid4()
        v = Version(
            id=v_id,
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )
        await repo.create(v)

        updated = await repo.update_status(v_id, "ready")
        assert updated is not None
        assert updated.status == VersionStatus.READY
        assert updated.error_message is None

        # Update to FAILED with error message
        updated_failed = await repo.update_status(v_id, "failed", error_message="Parse failed")
        assert updated_failed is not None
        assert updated_failed.status == VersionStatus.FAILED
        assert updated_failed.error_message == "Parse failed"

    async def test_exists(self, test_session: AsyncSession) -> None:
        doc = await self._setup_document(test_session)
        repo = SqlAlchemyVersionRepository(test_session)
        v_id = uuid4()

        assert await repo.exists(v_id) is False

        v = Version(
            id=v_id,
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await repo.create(v)
        assert await repo.exists(v_id) is True
