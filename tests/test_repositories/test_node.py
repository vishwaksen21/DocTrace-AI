"""Unit tests for SqlAlchemyNodeRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Document, Node, Version
from app.domain.enums import NodeType, VersionStatus
from app.repositories.document import SqlAlchemyDocumentRepository
from app.repositories.node import SqlAlchemyNodeRepository
from app.repositories.version import SqlAlchemyVersionRepository


@pytest.mark.anyio
class TestSqlAlchemyNodeRepository:
    """Tests for the SqlAlchemyNodeRepository."""

    async def _setup_version(self, session: AsyncSession) -> Version:
        doc_repo = SqlAlchemyDocumentRepository(session)
        ver_repo = SqlAlchemyVersionRepository(session)

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
        return await ver_repo.create(ver)

    def _node(
        self,
        version_id: uuid4,
        position: int,
        parent_id: uuid4 | None = None,
        node_type: NodeType = NodeType.PARAGRAPH,
        heading_level: int | None = None,
        content_hash: str | None = None,
    ) -> Node:
        return Node(
            id=uuid4(),
            version_id=version_id,
            node_type=node_type,
            content=f"Content {position}",
            content_hash=content_hash or f"hash_{position}".ljust(64, "0"),
            position_index=position,
            path=str(position),
            created_at=datetime.now(tz=UTC),
            parent_id=parent_id,
            heading_level=heading_level,
        )

    async def test_get_by_id_and_exists(self, test_session: AsyncSession) -> None:
        ver = await self._setup_version(test_session)
        repo = SqlAlchemyNodeRepository(test_session)
        node_id = uuid4()

        assert await repo.get_by_id(node_id) is None
        assert await repo.exists(node_id) is False

        node = Node(
            id=node_id,
            version_id=ver.id,
            node_type=NodeType.PARAGRAPH,
            content="Hello world",
            content_hash="h".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )

        await repo.bulk_create([node])

        assert await repo.exists(node_id) is True
        fetched = await repo.get_by_id(node_id)
        assert fetched is not None
        assert fetched.id == node_id
        assert fetched.content == "Hello world"
        assert fetched.node_type == NodeType.PARAGRAPH

    async def test_list_for_version(self, test_session: AsyncSession) -> None:
        ver = await self._setup_version(test_session)
        repo = SqlAlchemyNodeRepository(test_session)

        n1 = self._node(ver.id, position=0)
        n2 = self._node(ver.id, position=1)

        await repo.bulk_create([n1, n2])

        items, total = await repo.list_for_version(ver.id, offset=0, limit=1)
        assert total == 2
        assert len(items) == 1
        assert items[0].id == n1.id

        items, total = await repo.list_for_version(ver.id, offset=1, limit=1)
        assert total == 2
        assert len(items) == 1
        assert items[0].id == n2.id

    async def test_get_children(self, test_session: AsyncSession) -> None:
        ver = await self._setup_version(test_session)
        repo = SqlAlchemyNodeRepository(test_session)

        parent = self._node(ver.id, position=0, node_type=NodeType.HEADING, heading_level=1)
        await repo.bulk_create([parent])

        c1 = self._node(ver.id, position=1, parent_id=parent.id)
        c2 = self._node(ver.id, position=2, parent_id=parent.id)
        await repo.bulk_create([c1, c2])

        children = await repo.get_children(parent.id)
        assert len(children) == 2
        assert children[0].id == c1.id
        assert children[1].id == c2.id

    async def test_get_by_content_hash(self, test_session: AsyncSession) -> None:
        ver = await self._setup_version(test_session)
        repo = SqlAlchemyNodeRepository(test_session)

        c_hash = "abc".ljust(64, "0")
        node = self._node(ver.id, position=0, content_hash=c_hash)
        await repo.bulk_create([node])

        fetched = await repo.get_by_content_hash(ver.id, c_hash)
        assert fetched is not None
        assert fetched.id == node.id

        fetched_missing = await repo.get_by_content_hash(ver.id, "nonexistent".ljust(64, "0"))
        assert fetched_missing is None

    async def test_get_nodes_for_diff(self, test_session: AsyncSession) -> None:
        ver = await self._setup_version(test_session)
        repo = SqlAlchemyNodeRepository(test_session)

        # Insert out of order to verify sorting
        n2 = self._node(ver.id, position=2)
        n0 = self._node(ver.id, position=0)
        n1 = self._node(ver.id, position=1)

        await repo.bulk_create([n2, n0, n1])

        nodes = await repo.get_nodes_for_diff(ver.id)
        assert len(nodes) == 3
        # Check order is position index ascending
        assert [n.position_index for n in nodes] == [0, 1, 2]
        assert nodes[0].id == n0.id
        assert nodes[1].id == n1.id
        assert nodes[2].id == n2.id
