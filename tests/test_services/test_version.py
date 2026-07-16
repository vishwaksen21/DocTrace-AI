"""Unit tests for VersionService and the background parsing task."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Document, Node, Version
from app.domain.enums import NodeType, VersionStatus
from app.domain.exceptions import (
    BusinessValidationError,
    DocumentNotFoundError,
    NodeNotFoundError,
    VersionNotFoundError,
    VersionNotReadyError,
)
from app.parser.types import ParsedNode
from app.repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyNodeRepository,
    SqlAlchemyVersionRepository,
)
from app.services.version import (
    VersionService,
    parse_and_persist_version_task,
)


@pytest.mark.anyio
class TestVersionService:
    """Tests for the VersionService class."""

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

    async def test_create_version_success(self, service_session: AsyncSession) -> None:
        doc = await self._setup_document(service_session)
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = VersionService(ver_repo, node_repo, doc_repo)
        bg_tasks = MagicMock(spec=BackgroundTasks)

        v = await service.create_version(
            document_id=doc.id,
            upload_filename="doc_v1.pdf",
            pdf_bytes=b"test",
            background_tasks=bg_tasks,
        )

        assert v.id is not None
        assert v.document_id == doc.id
        assert v.version_number == 1
        assert v.status == VersionStatus.PROCESSING

        # Verify background task was scheduled
        bg_tasks.add_task.assert_called_once_with(
            parse_and_persist_version_task,
            version_id=v.id,
            pdf_bytes=b"test",
        )

    async def test_create_version_missing_document_raises(
        self,
        service_session: AsyncSession,
    ) -> None:
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = VersionService(ver_repo, node_repo, doc_repo)
        bg_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(DocumentNotFoundError):
            await service.create_version(
                document_id=uuid4(),
                upload_filename="test.pdf",
                pdf_bytes=b"test",
                background_tasks=bg_tasks,
            )

    async def test_get_version_and_raise_methods(self, service_session: AsyncSession) -> None:
        doc = await self._setup_document(service_session)
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = VersionService(ver_repo, node_repo, doc_repo)

        ver_id = uuid4()
        ver = Version(
            id=ver_id,
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(ver)

        assert await service.get_version(ver_id) is not None
        assert (await service.get_version_or_raise(ver_id)).version_number == 1

        with pytest.raises(VersionNotFoundError):
            await service.get_version_or_raise(uuid4())

    async def test_list_versions(self, service_session: AsyncSession) -> None:
        doc = await self._setup_document(service_session)
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = VersionService(ver_repo, node_repo, doc_repo)

        v1 = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(v1)

        items, total = await service.list_versions(doc.id, offset=0, limit=10)
        assert total == 1
        assert len(items) == 1

        with pytest.raises(DocumentNotFoundError):
            await service.list_versions(uuid4(), offset=0, limit=10)

    async def test_list_nodes_and_children_validations(self, service_session: AsyncSession) -> None:
        doc = await self._setup_document(service_session)
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = VersionService(ver_repo, node_repo, doc_repo)

        # 1. Version in PROCESSING status -> VersionNotReadyError
        v_proc_id = uuid4()
        v_proc = Version(
            id=v_proc_id,
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(v_proc)

        with pytest.raises(VersionNotReadyError):
            await service.list_nodes(v_proc_id, 0, 10)

        with pytest.raises(VersionNotReadyError):
            await service.get_node_children(v_proc_id, uuid4())

        # 2. Version in READY status but node missing
        v_ready_id = uuid4()
        v_ready = Version(
            id=v_ready_id,
            document_id=doc.id,
            version_number=2,
            upload_filename="v2.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(v_ready)

        with pytest.raises(NodeNotFoundError):
            await service.get_node_children(v_ready_id, uuid4())

        # 3. Node version mismatch -> BusinessValidationError
        other_ver_id = uuid4()
        other_ver = Version(
            id=other_ver_id,
            document_id=doc.id,
            version_number=3,
            upload_filename="v3.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(other_ver)

        other_node = Node(
            id=uuid4(),
            version_id=other_ver_id,
            node_type=NodeType.PARAGRAPH,
            content="Content",
            content_hash="h".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        await node_repo.bulk_create([other_node])

        with pytest.raises(BusinessValidationError):
            await service.get_node_children(v_ready_id, other_node.id)

    async def test_compare_versions(self, service_session: AsyncSession) -> None:
        doc = await self._setup_document(service_session)
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        service = VersionService(ver_repo, node_repo, doc_repo)

        # Create two READY versions of the same document
        v1_id = uuid4()
        v1 = Version(
            id=v1_id,
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(v1)

        v2_id = uuid4()
        v2 = Version(
            id=v2_id,
            document_id=doc.id,
            version_number=2,
            upload_filename="v2.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(v2)

        # Add nodes
        h = "h".ljust(64, "0")
        n1 = Node(
            id=uuid4(),
            version_id=v1_id,
            node_type=NodeType.PARAGRAPH,
            content="Text",
            content_hash=h,
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        n2 = Node(
            id=uuid4(),
            version_id=v2_id,
            node_type=NodeType.PARAGRAPH,
            content="Text",
            content_hash=h,
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )

        await node_repo.bulk_create([n1])
        await node_repo.bulk_create([n2])

        # Diff version 2 against version 1
        diffs = await service.compare_versions(new_version_id=v2_id, old_version_id=v1_id)
        assert len(diffs) == 1
        assert diffs[0].status == "unchanged"

        # Diff version 2 against implicit predecessor (which is version 1)
        diffs_implicit = await service.compare_versions(new_version_id=v2_id, old_version_id=None)
        assert len(diffs_implicit) == 1
        assert diffs_implicit[0].status == "unchanged"


@pytest.mark.anyio
class TestParseAndPersistVersionTask:
    """Tests for the parse_and_persist_version_task background task."""

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

    async def test_parse_success(self, service_session: AsyncSession) -> None:
        doc = await self._setup_document(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)

        # Create Version in PROCESSING status
        ver_id = uuid4()
        ver = Version(
            id=ver_id,
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(ver)
        await service_session.commit()  # commit so background task can fetch it

        # Setup parsed nodes to return
        parsed = [
            ParsedNode(
                node_type=NodeType.HEADING,
                content="Chapter 1",
                content_hash="h1".ljust(64, "0"),
                position_index=0,
                path="0",
                heading_level=1,
                parent_position_index=None,
            ),
            ParsedNode(
                node_type=NodeType.PARAGRAPH,
                content="Intro paragraph",
                content_hash="h2".ljust(64, "0"),
                position_index=1,
                path="0.0",
                heading_level=None,
                parent_position_index=0,
            ),
        ]

        with patch("app.parser.pdf_parser.parse_pdf", AsyncMock(return_value=parsed)):
            # Patch get_session so the background task uses our test_session
            # instead of creating a new unrelated connection
            mock_gen = AsyncMock()
            mock_gen.__aenter__.return_value = service_session
            with patch("app.services.version.get_session", return_value=mock_gen):
                await parse_and_persist_version_task(ver_id, b"pdf-bytes")

        # Verify status is READY and nodes are persisted
        refreshed_ver = await ver_repo.get_by_id(ver_id)
        assert refreshed_ver is not None
        assert refreshed_ver.status == VersionStatus.READY
        assert refreshed_ver.error_message is None

        nodes, total = await node_repo.list_for_version(ver_id, 0, 10)
        assert total == 2
        assert nodes[0].node_type == NodeType.HEADING
        assert nodes[1].node_type == NodeType.PARAGRAPH
        assert nodes[1].parent_id == nodes[0].id

    async def test_parse_failed_status_updated(self, service_session: AsyncSession) -> None:
        doc = await self._setup_document(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)

        # Create Version in PROCESSING status
        ver_id = uuid4()
        ver = Version(
            id=ver_id,
            document_id=doc.id,
            version_number=1,
            upload_filename="v1.pdf",
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(ver)
        await service_session.commit()

        # Mock parser raising exception
        with patch(
            "app.parser.pdf_parser.parse_pdf",
            AsyncMock(side_effect=ValueError("Corrupt PDF file structure")),
        ):
            mock_gen = AsyncMock()
            mock_gen.__aenter__.return_value = service_session
            with patch("app.services.version.get_session", return_value=mock_gen):
                await parse_and_persist_version_task(ver_id, b"corrupt-bytes")

        # Verify status is FAILED and carries error message
        refreshed_ver = await ver_repo.get_by_id(ver_id)
        assert refreshed_ver is not None
        assert refreshed_ver.status == VersionStatus.FAILED
        assert refreshed_ver.error_message == "Corrupt PDF file structure"
