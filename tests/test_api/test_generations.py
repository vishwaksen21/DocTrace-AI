"""Integration tests for QA Generations API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_llm_client
from app.domain.entities import Document, Node, Selection, Version
from app.domain.enums import NodeType, VersionStatus
from app.llm import LLMResponse
from app.main import app
from app.repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyNodeRepository,
    SqlAlchemySelectionRepository,
    SqlAlchemyVersionRepository,
)


@pytest.mark.anyio
class TestGenerationAPI:
    """API tests for the /generations and selections/generate endpoints."""

    async def _setup_selection(self, session: AsyncSession) -> Selection:
        doc_repo = SqlAlchemyDocumentRepository(session)
        ver_repo = SqlAlchemyVersionRepository(session)
        node_repo = SqlAlchemyNodeRepository(session)
        sel_repo = SqlAlchemySelectionRepository(session)

        doc = Document(
            id=uuid4(),
            title="Gen Doc",
            original_filename="gen.pdf",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        await doc_repo.create(doc)

        ver = Version(
            id=uuid4(),
            document_id=doc.id,
            version_number=1,
            upload_filename="gen_v1.pdf",
            status=VersionStatus.READY,
            created_at=datetime.now(tz=UTC),
        )
        await ver_repo.create(ver)

        n1 = Node(
            id=uuid4(),
            version_id=ver.id,
            node_type=NodeType.PARAGRAPH,
            content="Requirements text",
            content_hash="h1".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        await node_repo.bulk_create([n1])

        sel = Selection(
            id=uuid4(),
            version_id=ver.id,
            node_ids=(n1.id,),
            created_at=datetime.now(tz=UTC),
            name="QA Scope",
        )
        saved_sel = await sel_repo.create(sel)
        await session.commit()
        return saved_sel

    async def test_trigger_and_get_generation(
        self, client: AsyncClient, api_session: AsyncSession, mock_mongo_db: MagicMock
    ) -> None:
        sel = await self._setup_selection(api_session)

        # Mock LLM Client Dependency - use AsyncMock so complete() is awaitable
        mock_llm = AsyncMock()
        mock_llm.model = "google/gemini-2.5-flash"

        # Prepare structured test case output matching expected response schema format
        import json

        node_id = str(sel.node_ids[0])
        llm_json = json.dumps(
            {
                "test_cases": [
                    {
                        "id": "tc-001",
                        "title": "Verify spec",
                        "objective": "Verify specification requirements",
                        "preconditions": [],
                        "steps": ["Step 1"],
                        "expected_result": "Match",
                        "node_refs": [node_id],
                    }
                ]
            }
        )

        response = LLMResponse(
            content=llm_json,
            model=mock_llm.model,
            prompt_tokens=30,
            completion_tokens=15,
            duration_ms=200.0,
            raw_response={"choices": []},
        )
        mock_llm.complete.return_value = response

        app.dependency_overrides[get_llm_client] = lambda: mock_llm

        try:
            # 1. Trigger QA Generation
            res_trigger = await client.post(f"/api/v1/selections/{sel.id}/generate")
            assert res_trigger.status_code == 202
            data = res_trigger.json()
            assert data["status"] == "processing"
            generation_id = data["id"]
            assert generation_id is not None

            # Mock MongoDB find_one for get generation endpoint call
            from bson import ObjectId

            mock_doc = {
                "_id": ObjectId(generation_id),
                "selection_id": str(sel.id),
                "document_id": str(uuid4()),
                "version_id": str(sel.version_id),
                "model": "google/gemini-2.5-flash",
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "status": "processing",
                "raw_response": "{}",
                "test_cases": [],
                "validation_errors": [],
                "created_at": datetime.now(tz=UTC).isoformat(),
                "duration_ms": 1500.0,
            }
            mock_mongo_db["generations"].find_one.return_value = mock_doc

            # 2. Get generation status
            res_get = await client.get(f"/api/v1/generations/{generation_id}")
            assert res_get.status_code == 200
            assert res_get.json()["id"] == generation_id

            # Since the background task runs asynchronously in the ASGI loop,
            # it might still be 'processing' or completed. Let's assert keys exist.
            assert "status" in res_get.json()
            assert "test_cases" in res_get.json()

        finally:
            if get_llm_client in app.dependency_overrides:
                del app.dependency_overrides[get_llm_client]

    async def test_list_generations_empty(
        self, client: AsyncClient, api_session: AsyncSession
    ) -> None:
        sel = await self._setup_selection(api_session)

        response = await client.get(f"/api/v1/selections/{sel.id}/generations")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] == 0

    async def test_get_generation_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/generations/507f1f77bcf86cd799439011")
        assert response.status_code == 404
        assert response.json()["error"] == "NotFound"
