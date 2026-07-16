"""Unit tests for GenerationService and the background generation task."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Document, Node, Selection, Version
from app.domain.enums import NodeType, VersionStatus
from app.domain.exceptions import (
    GenerationNotFoundError,
    SelectionNotFoundError,
)
from app.llm.base import LLMResponse
from app.repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyNodeRepository,
    SqlAlchemySelectionRepository,
    SqlAlchemyVersionRepository,
)
from app.services.generation import (
    GenerationService,
    generate_qa_cases_task,
)


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Provide a mock LLM client conforming to LLMClientProtocol."""
    client = MagicMock()
    client.model = "google/gemini-2.5-flash"
    client.complete = AsyncMock()
    return client


@pytest.mark.anyio
class TestGenerationService:
    """Tests for the GenerationService class."""

    async def _setup_selection(self, session: AsyncSession) -> Selection:
        doc_repo = SqlAlchemyDocumentRepository(session)
        ver_repo = SqlAlchemyVersionRepository(session)
        node_repo = SqlAlchemyNodeRepository(session)
        sel_repo = SqlAlchemySelectionRepository(session)

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
        await node_repo.bulk_create([n1])

        sel = Selection(
            id=uuid4(),
            version_id=saved_ver.id,
            node_ids=(n1.id,),
            created_at=datetime.now(tz=UTC),
            name="QA Scope",
        )
        return await sel_repo.create(sel)

    async def test_trigger_generation_success(
        self,
        service_session: AsyncSession,
        mock_llm_client: MagicMock,
    ) -> None:
        sel = await self._setup_selection(service_session)
        sel_repo = SqlAlchemySelectionRepository(service_session)

        # Mock MongoDB repository
        mock_mongo_repo = MagicMock()
        mock_mongo_repo.create = AsyncMock(
            return_value=MagicMock(id="mongo-id-123", model=mock_llm_client.model)
        )

        service = GenerationService(mock_mongo_repo, sel_repo, mock_llm_client)
        bg_tasks = MagicMock(spec=BackgroundTasks)

        result = await service.trigger_generation(sel.id, bg_tasks)

        assert result is not None
        assert result.id == "mongo-id-123"
        bg_tasks.add_task.assert_called_once_with(
            generate_qa_cases_task,
            generation_id="mongo-id-123",
            selection_id=sel.id,
            llm_client=mock_llm_client,
        )

    async def test_trigger_generation_missing_selection_raises(
        self,
        service_session: AsyncSession,
        mock_llm_client: MagicMock,
    ) -> None:
        sel_repo = SqlAlchemySelectionRepository(service_session)
        mock_mongo_repo = MagicMock()

        service = GenerationService(mock_mongo_repo, sel_repo, mock_llm_client)
        bg_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(SelectionNotFoundError):
            await service.trigger_generation(uuid4(), bg_tasks)

    async def test_get_generation_methods(
        self,
        service_session: AsyncSession,
        mock_llm_client: MagicMock,
    ) -> None:
        sel_repo = SqlAlchemySelectionRepository(service_session)
        mock_mongo_repo = MagicMock()
        mock_mongo_repo.get_by_id = AsyncMock(
            side_effect=lambda gid: gid if gid == "exists" else None
        )

        service = GenerationService(mock_mongo_repo, sel_repo, mock_llm_client)

        assert await service.get_generation("exists") == "exists"
        assert await service.get_generation("missing") is None

        with pytest.raises(GenerationNotFoundError):
            await service.get_generation_or_raise("missing")

    async def test_list_generations(
        self,
        service_session: AsyncSession,
        mock_llm_client: MagicMock,
    ) -> None:
        sel = await self._setup_selection(service_session)
        sel_repo = SqlAlchemySelectionRepository(service_session)

        mock_mongo_repo = MagicMock()
        mock_mongo_repo.list_for_selection = AsyncMock(return_value=([], 0))

        service = GenerationService(mock_mongo_repo, sel_repo, mock_llm_client)

        _results, total = await service.list_generations(sel.id, offset=0, limit=10)
        assert total == 0

        with pytest.raises(SelectionNotFoundError):
            await service.list_generations(uuid4(), offset=0, limit=10)


@pytest.mark.anyio
class TestGenerateQACasesTask:
    """Tests for the generate_qa_cases_task background task."""

    async def test_generation_task_success(
        self,
        service_session: AsyncSession,
        mock_llm_client: MagicMock,
    ) -> None:
        # Create parent selection and node in SQLite
        doc_repo = SqlAlchemyDocumentRepository(service_session)
        ver_repo = SqlAlchemyVersionRepository(service_session)
        node_repo = SqlAlchemyNodeRepository(service_session)
        sel_repo = SqlAlchemySelectionRepository(service_session)

        doc = Document(
            id=uuid4(),
            title="Doc",
            original_filename="doc.pdf",
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
            content="System requirements section",
            content_hash="h1".ljust(64, "0"),
            position_index=0,
            path="0",
            created_at=datetime.now(tz=UTC),
        )
        await node_repo.bulk_create([n1])

        sel = Selection(
            id=uuid4(),
            version_id=saved_ver.id,
            node_ids=(n1.id,),
            created_at=datetime.now(tz=UTC),
            name="QA Scope",
        )
        saved_sel = await sel_repo.create(sel)
        await service_session.commit()

        # Mock LLM complete response content
        llm_json = f"""{{
            "test_cases": [
                {{
                    "id": "tc-001",
                    "title": "Verify requirements",
                    "objective": "Verify system requirements",
                    "preconditions": ["System is online"],
                    "steps": ["Step 1", "Step 2"],
                    "expected_result": "Success outcome",
                    "node_refs": ["{n1.id!s}"]
                }}
            ]
        }}"""

        response = LLMResponse(
            content=llm_json,
            model="google/gemini-2.5-flash",
            prompt_tokens=50,
            completion_tokens=20,
            duration_ms=450.0,
            raw_response={"choices": []},
        )
        mock_llm_client.complete.return_value = response

        # Mock Mongo repository update status
        mock_mongo_instance = MagicMock()
        mock_mongo_instance.update_status = AsyncMock()

        repo_patch = patch(
            "app.repositories.generation.MongoGenerationRepository",
            return_value=mock_mongo_instance,
        )
        with repo_patch:
            mock_gen = AsyncMock()
            mock_gen.__aenter__.return_value = service_session
            with patch("app.services.generation.get_session", return_value=mock_gen):
                await generate_qa_cases_task("mongo-gen-id", saved_sel.id, mock_llm_client)

        # Assert status was updated to SUCCESS
        mock_mongo_instance.update_status.assert_called_once()
        _args, kwargs = mock_mongo_instance.update_status.call_args
        assert kwargs["generation_id"] == "mongo-gen-id"
        assert kwargs["status"].value == "success"
        assert len(kwargs["updates"]["test_cases"]) == 1
        assert kwargs["updates"]["test_cases"][0].id == "tc-001"
