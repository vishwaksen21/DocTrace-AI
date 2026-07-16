"""Integration tests for Selection API endpoints."""

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
class TestSelectionAPI:
    """API tests for the /selections resource."""

    async def _setup_version_and_nodes(
        self, session: AsyncSession
    ) -> tuple[Version, list[Node]]:
        doc_repo = SqlAlchemyDocumentRepository(session)
        ver_repo = SqlAlchemyVersionRepository(session)
        node_repo = SqlAlchemyNodeRepository(session)

        doc = Document(
            id=uuid4(),
            title="Selection Doc",
            original_filename="selection.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        await doc_repo.create(doc)

        ver = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=1,
            upload_filename="sel_v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(ver)

        n1 = Node(
            id=uuid4(),
            version_id=ver.id,
            node_type=NodeType.PARAGRAPH,
            content="Block 1 content",
            content_hash="h1".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        n2 = Node(
            id=uuid4(),
            version_id=ver.id,
            node_type=NodeType.PARAGRAPH,
            content="Block 2 content",
            content_hash="h2".ljust(64, "0"),
            position_index=1,
            path="1",
            created_at=datetime.now(tz=UTC),
        )

        nodes = await node_repo.bulk_create([n1, n2])
        await session.commit()
        return ver, nodes

    async def test_create_and_get_selection_success(
        self, client: AsyncClient, api_session: AsyncSession
    ) -> None:
        ver, nodes = await self._setup_version_and_nodes(api_session)

        # 1. Create selection
        payload = {
            "version_id": str(ver.id),
            "node_ids": [str(nodes[0].id), str(nodes[1].id)],
            "name": "Audit Scope",
        }
        res_create = await client.post("/api/v1/selections", json=payload)
        assert res_create.status_code == 201
        data = res_create.json()
        assert data["name"] == "Audit Scope"
        assert len(data["node_ids"]) == 2
        selection_id = data["id"]

        # 2. Get selection details
        response = await client.get(f"/api/v1/selections/{selection_id}")
        assert response.status_code == 200
        get_data = response.json()
        assert get_data["id"] == selection_id
        assert "nodes" in get_data
        assert len(get_data["nodes"]) == 2
        assert get_data["nodes"][0]["content"] == "Block 1 content"

    async def test_create_selection_empty_nodes_validation(self, client: AsyncClient) -> None:
        payload = {
            "version_id": str(uuid4()),
            "node_ids": [],
            "name": "Empty Scope",
        }
        response = await client.post("/api/v1/selections", json=payload)
        # Pydantic validation error triggers 422
        assert response.status_code == 422

    async def test_get_selection_not_found(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/v1/selections/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["error"] == "NotFound"
