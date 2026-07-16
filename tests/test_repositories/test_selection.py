"""Unit tests for SqlAlchemySelectionRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Document, Node, Selection, Version
from app.domain.enums import NodeType, VersionStatus
from app.repositories.document import SqlAlchemyDocumentRepository
from app.repositories.node import SqlAlchemyNodeRepository
from app.repositories.selection import SqlAlchemySelectionRepository
from app.repositories.version import SqlAlchemyVersionRepository


@pytest.mark.anyio
class TestSqlAlchemySelectionRepository:
    """Tests for the SqlAlchemySelectionRepository."""

    async def _setup_version_and_nodes(self, session: AsyncSession) -> tuple[Version, list[Node]]:
        doc_repo = SqlAlchemyDocumentRepository(session)
        ver_repo = SqlAlchemyVersionRepository(session)
        node_repo = SqlAlchemyNodeRepository(session)

        doc = Document(
            id=uuid4(),
            title="Parent Doc",
            original_filename="parent.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        saved_doc = await doc_repo.create(doc)

        ver = Version(
            id=uuid4(),
            document_id=saved_doc.id,
            version_number=1,
            upload_filename="upload_v1.pdf",
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )
        saved_ver = await ver_repo.create(ver)

        n1 = Node(
            id=uuid4(),
            version_id=saved_ver.id,
            node_type=NodeType.PARAGRAPH,
            content="Para 1",
            content_hash="h1".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        n2 = Node(
            id=uuid4(),
            version_id=saved_ver.id,
            node_type=NodeType.PARAGRAPH,
            content="Para 2",
            content_hash="h2".ljust(64, "0"),
            position_index=1,
            path="1",
            created_at=datetime.now(tz=UTC),
        )
        saved_nodes = await node_repo.bulk_create([n1, n2])
        return saved_ver, saved_nodes

    async def test_create_and_get_by_id(self, test_session: AsyncSession) -> None:
        ver, nodes = await self._setup_version_and_nodes(test_session)
        repo = SqlAlchemySelectionRepository(test_session)

        selection_id = uuid4()
        sel = Selection(
            id=selection_id,
            version_id=ver.id,
            node_ids=(nodes[0].id, nodes[1].id),
            created_at=datetime.now(tz=UTC),
            name="QA Scope",
        )

        saved = await repo.create(sel)
        assert saved.id == selection_id
        assert saved.version_id == ver.id
        assert saved.name == "QA Scope"
        assert len(saved.node_ids) == 2
        # Verify node ordering in the selection
        assert saved.node_ids == (nodes[0].id, nodes[1].id)

        fetched = await repo.get_by_id(selection_id)
        assert fetched is not None
        assert fetched.id == selection_id
        assert fetched.node_ids == (nodes[0].id, nodes[1].id)

    async def test_get_by_id_missing_returns_none(self, test_session: AsyncSession) -> None:
        repo = SqlAlchemySelectionRepository(test_session)
        assert await repo.get_by_id(uuid4()) is None

    async def test_list_for_version(self, test_session: AsyncSession) -> None:
        ver, nodes = await self._setup_version_and_nodes(test_session)
        repo = SqlAlchemySelectionRepository(test_session)

        s1 = Selection(
            id=uuid4(),
            version_id=ver.id,
            node_ids=(nodes[0].id,),
            created_at=datetime.now(tz=UTC),
            name="Sel 1",
        )
        s2 = Selection(
            id=uuid4(),
            version_id=ver.id,
            node_ids=(nodes[1].id,),
            created_at=datetime.now(tz=UTC),
            name="Sel 2",
        )

        await repo.create(s1)
        await repo.create(s2)

        items1, total = await repo.list_for_version(ver.id, offset=0, limit=1)
        assert total == 2
        assert len(items1) == 1

        items2, total = await repo.list_for_version(ver.id, offset=1, limit=1)
        assert total == 2
        assert len(items2) == 1

        assert {items1[0].id, items2[0].id} == {s1.id, s2.id}

    async def test_exists_and_delete(self, test_session: AsyncSession) -> None:
        ver, nodes = await self._setup_version_and_nodes(test_session)
        repo = SqlAlchemySelectionRepository(test_session)
        selection_id = uuid4()

        assert await repo.exists(selection_id) is False

        sel = Selection(
            id=selection_id,
            version_id=ver.id,
            node_ids=(nodes[0].id,),
            created_at=datetime.now(tz=UTC),
            name="Temp Sel",
        )

        await repo.create(sel)
        assert await repo.exists(selection_id) is True

        # Delete selection
        await repo.delete(selection_id)

        assert await repo.exists(selection_id) is False
        assert await repo.get_by_id(selection_id) is None

        # Verify junction rows are deleted Cascade style
        count = await test_session.execute(
            text("SELECT COUNT(*) FROM selection_nodes WHERE selection_id = :sid"),
            {"sid": str(selection_id)},
        )
        assert count.scalar() == 0

        # Verify parent node is NOT deleted
        node_repo = SqlAlchemyNodeRepository(test_session)
        assert await node_repo.exists(nodes[0].id) is True
