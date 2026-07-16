"""Integration tests for Version nodes and comparison diff API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Document, Node, Version
from app.domain.enums import NodeType, VersionStatus
from app.repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyNodeRepository,
    SqlAlchemyVersionRepository,
)


@pytest.mark.anyio
class TestVersionAPI:
    """API tests for the /versions resource."""

    async def _setup_ready_version_with_nodes(
        self, session: AsyncSession
    ) -> tuple[Version, list[Node]]:
        doc_repo = SqlAlchemyDocumentRepository(session)
        ver_repo = SqlAlchemyVersionRepository(session)
        node_repo = SqlAlchemyNodeRepository(session)

        doc = Document(
            id=uuid4(),
            title="API Specs",
            original_filename="specs.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        await doc_repo.create(doc)

        ver = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=1,
            upload_filename="specs_v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(ver)

        n1 = Node(
            id=uuid4(),
            version_id=ver.id,
            node_type=NodeType.HEADING,
            heading_level=1,
            content="1. Introduction",
            content_hash="h1".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        n2 = Node(
            id=uuid4(),
            version_id=ver.id,
            node_type=NodeType.PARAGRAPH,
            content="This is introductory body paragraph text.",
            content_hash="h2".ljust(64, "0"),
            position_index=1,
            path="0.0",
            created_at=datetime.now(tz=UTC),
        )

        nodes = await node_repo.bulk_create([n1, n2])
        await session.commit()
        return ver, nodes

    async def test_get_version_nodes_success(
        self, client: AsyncClient, api_session: AsyncSession
    ) -> None:
        ver, nodes = await self._setup_ready_version_with_nodes(api_session)

        response = await client.get(f"/api/v1/versions/{ver.id}/nodes?offset=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == str(nodes[0].id)
        assert data["items"][1]["id"] == str(nodes[1].id)

    async def test_get_version_nodes_not_ready_raises(
        self, client: AsyncClient, api_session: AsyncSession
    ) -> None:
        # Create a document and version in PROCESSING status
        doc_repo = SqlAlchemyDocumentRepository(api_session)
        ver_repo = SqlAlchemyVersionRepository(api_session)

        doc = Document(
            id=uuid4(),
            title="Processing Doc",
            original_filename="proc.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        await doc_repo.create(doc)

        ver = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=1,
            upload_filename="proc_v1.pdf",
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(ver)
        await api_session.commit()

        response = await client.get(f"/api/v1/versions/{ver.id}/nodes")
        assert response.status_code == 422
        assert response.json()["error"] == "ValidationError"
        assert "is not ready" in response.json()["message"]

    async def test_diff_version_success(
        self, client: AsyncClient, api_session: AsyncSession
    ) -> None:
        # Setup version 1 with nodes
        ver1, _nodes1 = await self._setup_ready_version_with_nodes(api_session)

        # Setup version 2 of same document with modified content
        ver_repo = SqlAlchemyVersionRepository(api_session)
        node_repo = SqlAlchemyNodeRepository(api_session)

        ver2 = Version(
            id=uuid4(),
            document_id=ver1.document_id,
            version_number=2,
            upload_filename="specs_v2.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(ver2)

        n1 = Node(
            id=uuid4(),
            version_id=ver2.id,
            node_type=NodeType.HEADING,
            heading_level=1,
            content="1. Introduction",
            content_hash="h1".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        # modified content
        n2 = Node(
            id=uuid4(),
            version_id=ver2.id,
            node_type=NodeType.PARAGRAPH,
            content="This body text has changed.",
            content_hash="changed_hash".ljust(64, "0"),
            position_index=1,
            path="0.0",
            created_at=datetime.now(tz=UTC),
        )
        await node_repo.bulk_create([n1, n2])
        await api_session.commit()

        # Call diff endpoint for version 2 (will diff against version 1 predecessor)
        response = await client.get(f"/api/v1/versions/{ver2.id}/diff")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # heading remains unchanged
        assert data[0]["status"] == "unchanged"
        # paragraph is modified
        assert data[1]["status"] == "modified"
        assert data[1]["content_changed"] is True
