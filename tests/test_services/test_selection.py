"""Unit tests for SelectionService."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Document, Node, Version
from app.domain.enums import NodeType, VersionStatus
from app.domain.exceptions import (
    CrossVersionSelectionError,
    EmptySelectionError,
    NodeNotFoundError,
    SelectionNotFoundError,
    VersionNotFoundError,
    VersionNotReadyError,
)
from app.repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyNodeRepository,
    SqlAlchemySelectionRepository,
    SqlAlchemyVersionRepository,
)
from app.services.selection import SelectionService


@pytest.mark.anyio
class TestSelectionService:
    """Tests for the SelectionService class."""

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
            status=VersionStatus.READY,
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

    async def test_create_and_get_selection(self, service_session: AsyncSession) -> None:
        ver, nodes = await self._setup_version_and_nodes(service_session)
        sel_repo = SqlAlchemySelectionRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = SelectionService(sel_repo, ver_repo, node_repo)

        sel = await service.create_selection(
            version_id=ver.id,
            node_ids=[nodes[0].id, nodes[1].id],
            name="Target Scope",
        )

        assert sel.id is not None
        assert sel.version_id == ver.id
        assert sel.name == "Target Scope"
        assert sel.node_ids == (nodes[0].id, nodes[1].id)

        # Get it back
        fetched = await service.get_selection_or_raise(sel.id)
        assert fetched.id == sel.id
        assert fetched.node_ids == (nodes[0].id, nodes[1].id)

    async def test_create_empty_raises(self, service_session: AsyncSession) -> None:
        sel_repo = SqlAlchemySelectionRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = SelectionService(sel_repo, ver_repo, node_repo)

        with pytest.raises(EmptySelectionError):
            await service.create_selection(version_id=uuid4(), node_ids=[])

    async def test_create_missing_version_raises(self, service_session: AsyncSession) -> None:
        sel_repo = SqlAlchemySelectionRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = SelectionService(sel_repo, ver_repo, node_repo)

        with pytest.raises(VersionNotFoundError):
            await service.create_selection(version_id=uuid4(), node_ids=[uuid4()])

    async def test_create_not_ready_version_raises(self, service_session: AsyncSession) -> None:
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)
        sel_repo = SqlAlchemySelectionRepository(service_session)

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

        service = SelectionService(sel_repo, ver_repo, node_repo)

        with pytest.raises(VersionNotReadyError):
            await service.create_selection(version_id=saved_ver.id, node_ids=[uuid4()])

    async def test_create_missing_node_raises(self, service_session: AsyncSession) -> None:
        ver, _ = await self._setup_version_and_nodes(service_session)
        sel_repo = SqlAlchemySelectionRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = SelectionService(sel_repo, ver_repo, node_repo)

        with pytest.raises(NodeNotFoundError):
            await service.create_selection(version_id=ver.id, node_ids=[uuid4()])

    async def test_create_cross_version_raises(self, service_session: AsyncSession) -> None:
        ver1, nodes1 = await self._setup_version_and_nodes(service_session)

        # Create a second version and node
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)
        sel_repo = SqlAlchemySelectionRepository(service_session)

        ver2 = Version(
            id=uuid4(),
            document_id=ver1.document_id,
            version_number=2,
            upload_filename="v2.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        saved_ver2 = await ver_repo.create(ver2)

        n3 = Node(
            id=uuid4(),
            version_id=saved_ver2.id,
            node_type=NodeType.PARAGRAPH,
            content="Para 3",
            content_hash="h3".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        saved_n3 = await node_repo.bulk_create([n3])

        service = SelectionService(sel_repo, ver_repo, node_repo)

        with pytest.raises(CrossVersionSelectionError):
            # Attempt to create selection in version 1 but include node from version 2
            await service.create_selection(
                version_id=ver1.id,
                node_ids=[nodes1[0].id, saved_n3[0].id],
            )

    async def test_get_selection_missing_raises(self, service_session: AsyncSession) -> None:
        sel_repo = SqlAlchemySelectionRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = SelectionService(sel_repo, ver_repo, node_repo)

        with pytest.raises(SelectionNotFoundError):
            await service.get_selection_or_raise(uuid4())

    async def test_list_selections(self, service_session: AsyncSession) -> None:
        ver, nodes = await self._setup_version_and_nodes(service_session)
        sel_repo = SqlAlchemySelectionRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = SelectionService(sel_repo, ver_repo, node_repo)

        await service.create_selection(version_id=ver.id, node_ids=[nodes[0].id], name="Sel 1")

        items, total = await service.list_selections(ver.id, offset=0, limit=10)
        assert total == 1
        assert len(items) == 1

        with pytest.raises(VersionNotFoundError):
            await service.list_selections(uuid4(), offset=0, limit=10)
