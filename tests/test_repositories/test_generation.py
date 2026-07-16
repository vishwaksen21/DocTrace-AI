"""Unit tests for MongoGenerationRepository using mocks."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from bson import ObjectId

from app.domain.entities import GenerationResult, QATestCase
from app.domain.enums import GenerationStatus
from app.repositories.generation import MongoGenerationRepository


@pytest.fixture
def mock_db() -> MagicMock:
    """Provide a mock database and collection."""
    db = MagicMock()
    collection = MagicMock()
    db.__getitem__ = MagicMock(return_value=collection)
    return db


class TestMongoGenerationRepository:
    """Tests for MongoGenerationRepository using mocked Motor client."""

    @pytest.mark.anyio
    async def test_get_by_id_success(self, mock_db: MagicMock) -> None:
        repo = MongoGenerationRepository()
        gen_id = str(ObjectId())

        mock_doc = {
            "_id": ObjectId(gen_id),
            "selection_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "model": "google/gemini-2.5-flash",
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "status": "success",
            "raw_response": '{"test": "response"}',
            "test_cases": [
                {
                    "id": "tc-1",
                    "title": "TC 1",
                    "objective": "Verify behavior",
                    "preconditions": ["User is logged in"],
                    "steps": ["Step 1"],
                    "expected_result": "Result 1",
                    "node_refs": [str(uuid4())],
                }
            ],
            "validation_errors": [],
            "created_at": datetime.now(tz=UTC).isoformat(),
            "duration_ms": 1500.0,
        }

        mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=mock_doc)

        with patch("app.repositories.generation.get_database", return_value=mock_db):
            result = await repo.get_by_id(gen_id)

            assert result is not None
            assert result.id == gen_id
            assert result.model == "google/gemini-2.5-flash"
            assert result.status == GenerationStatus.SUCCESS
            assert len(result.test_cases) == 1
            assert result.test_cases[0].title == "TC 1"

            mock_db.__getitem__.return_value.find_one.assert_awaited_once_with(
                {"_id": ObjectId(gen_id)}
            )

    @pytest.mark.anyio
    async def test_get_by_id_invalid_id_returns_none(self) -> None:
        repo = MongoGenerationRepository()
        assert await repo.get_by_id("invalid-hex-id") is None

    @pytest.mark.anyio
    async def test_list_for_selection(self, mock_db: MagicMock) -> None:
        repo = MongoGenerationRepository()
        sel_id = uuid4()

        mock_doc = {
            "_id": ObjectId(),
            "selection_id": str(sel_id),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "model": "gpt-4",
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "status": "success",
            "raw_response": "{}",
            "test_cases": [],
            "validation_errors": [],
            "created_at": datetime.now(tz=UTC).isoformat(),
            "duration_ms": 100.0,
        }

        mock_collection = mock_db.__getitem__.return_value
        mock_collection.count_documents = AsyncMock(return_value=1)

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[mock_doc])
        mock_collection.find.return_value = mock_cursor

        with patch("app.repositories.generation.get_database", return_value=mock_db):
            results, total = await repo.list_for_selection(sel_id, offset=0, limit=10)

            assert total == 1
            assert len(results) == 1
            assert results[0].selection_id == sel_id

            mock_collection.count_documents.assert_awaited_once_with({"selection_id": str(sel_id)})
            mock_collection.find.assert_called_once_with({"selection_id": str(sel_id)})

    @pytest.mark.anyio
    async def test_create(self, mock_db: MagicMock) -> None:
        repo = MongoGenerationRepository()
        inserted_oid = ObjectId()

        tc = QATestCase(
            id="tc-1",
            title="Title",
            objective="Objective",
            preconditions=("Pre 1",),
            steps=("Step 1",),
            expected_result="Expected",
            node_refs=(uuid4(),),
        )

        result_entity = GenerationResult(
            selection_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            model="test-model",
            prompt_tokens=200,
            completion_tokens=100,
            status=GenerationStatus.SUCCESS,
            raw_response="raw",
            test_cases=(tc,),
            validation_errors=(),
            created_at=datetime.now(tz=UTC),
            duration_ms=500.0,
        )

        mock_collection = mock_db.__getitem__.return_value
        insert_res = MagicMock()
        insert_res.inserted_id = inserted_oid
        mock_collection.insert_one = AsyncMock(return_value=insert_res)

        with patch("app.repositories.generation.get_database", return_value=mock_db):
            saved = await repo.create(result_entity)

            assert saved.id == str(inserted_oid)
            assert saved.model == "test-model"
            assert len(saved.test_cases) == 1

            mock_collection.insert_one.assert_awaited_once()

    @pytest.mark.anyio
    async def test_update_status(self, mock_db: MagicMock) -> None:
        repo = MongoGenerationRepository()
        gen_id = str(ObjectId())
        new_status = "success"

        tc = QATestCase(
            id="tc-updated",
            title="Updated Title",
            objective="Updated Obj",
            preconditions=("Pre",),
            steps=("Step",),
            expected_result="Result",
            node_refs=(uuid4(),),
        )

        updates = {
            "prompt_tokens": 150,
            "completion_tokens": 75,
            "test_cases": (tc,),
            "validation_errors": ["Error 1"],
            "custom_uuid": uuid4(),
            "custom_date": datetime.now(tz=UTC),
        }

        mock_updated_doc = {
            "_id": ObjectId(gen_id),
            "selection_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "model": "gpt-4",
            "prompt_tokens": 150,
            "completion_tokens": 75,
            "status": new_status,
            "raw_response": "{}",
            "test_cases": [
                {
                    "id": "tc-updated",
                    "title": "Updated Title",
                    "objective": "Updated Obj",
                    "preconditions": ["Pre"],
                    "steps": ["Step"],
                    "expected_result": "Result",
                    "node_refs": [str(updates["custom_uuid"])],
                }
            ],
            "validation_errors": ["Error 1"],
            "created_at": datetime.now(tz=UTC).isoformat(),
            "duration_ms": 100.0,
        }

        mock_collection = mock_db.__getitem__.return_value
        mock_collection.find_one_and_update = AsyncMock(return_value=mock_updated_doc)

        with patch("app.repositories.generation.get_database", return_value=mock_db):
            updated_res = await repo.update_status(gen_id, new_status, updates)

            assert updated_res is not None
            assert updated_res.status == GenerationStatus.SUCCESS
            assert updated_res.prompt_tokens == 150
            assert len(updated_res.test_cases) == 1
            assert updated_res.test_cases[0].id == "tc-updated"

            mock_collection.find_one_and_update.assert_awaited_once()
