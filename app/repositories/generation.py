"""MongoDB implementation of the Generation repository.

Implements the ``GenerationRepositoryProtocol`` for storing LLM QA generation
artifacts in MongoDB using Motor.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.core.constants import MONGO_COLLECTION_GENERATIONS
from app.domain.entities import GenerationResult, QATestCase
from app.domain.enums import GenerationStatus
from app.infrastructure.mongodb import get_database


def _from_mongo_doc(doc: dict[str, Any]) -> GenerationResult:
    """Map a MongoDB BSON document to a GenerationResult domain entity."""
    created_at_raw = doc["created_at"]
    if isinstance(created_at_raw, str):
        created_at = datetime.fromisoformat(created_at_raw)
    else:
        created_at = created_at_raw

    test_cases = tuple(
        QATestCase(
            id=tc["id"],
            title=tc["title"],
            objective=tc["objective"],
            preconditions=tuple(tc["preconditions"]),
            steps=tuple(tc["steps"]),
            expected_result=tc["expected_result"],
            node_refs=tuple(UUID(r) for r in tc.get("node_refs", [])),
        )
        for tc in doc.get("test_cases", [])
    )

    return GenerationResult(
        id=str(doc["_id"]),
        selection_id=UUID(doc["selection_id"]),
        document_id=UUID(doc["document_id"]),
        version_id=UUID(doc["version_id"]),
        model=doc["model"],
        prompt_tokens=doc["prompt_tokens"],
        completion_tokens=doc["completion_tokens"],
        status=GenerationStatus(doc["status"]),
        raw_response=doc["raw_response"],
        test_cases=test_cases,
        validation_errors=tuple(doc.get("validation_errors", [])),
        created_at=created_at,
        duration_ms=doc["duration_ms"],
    )


class MongoGenerationRepository:
    """MongoDB implementation of the Generation repository using Motor."""

    async def get_by_id(self, generation_id: str) -> GenerationResult | None:
        """Return the generation result with the given MongoDB ObjectId string."""
        try:
            obj_id = ObjectId(generation_id)
        except (InvalidId, TypeError):
            return None

        db = get_database()
        collection = db[MONGO_COLLECTION_GENERATIONS]
        doc = await collection.find_one({"_id": obj_id})
        if doc is None:
            return None
        return _from_mongo_doc(doc)

    async def list_for_selection(
        self,
        selection_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[GenerationResult], int]:
        """Return a paginated list of generation results for a selection.

        Ordered by ``created_at`` descending (newest first).

        Args:
            selection_id: The parent selection's UUID.
            offset: Zero-based page offset.
            limit: Maximum items per page.

        Returns:
            ``(results, total_count)``
        """
        db = get_database()
        collection = db[MONGO_COLLECTION_GENERATIONS]
        query = {"selection_id": str(selection_id)}

        total_count = await collection.count_documents(query)

        cursor = collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
        docs = await cursor.to_list(length=limit)

        return [_from_mongo_doc(d) for d in docs], total_count

    async def create(self, result: GenerationResult) -> GenerationResult:
        """Persist a new generation result in MongoDB.

        Args:
            result: The result to store.  The MongoDB ``_id`` is assigned
                by the driver; ``result.id`` may be ``None`` before save.

        Returns:
            The persisted result with ``id`` set to the assigned ObjectId string.
        """
        doc = result.to_mongo_doc()
        if "_id" in doc:
            del doc["_id"]

        db = get_database()
        collection = db[MONGO_COLLECTION_GENERATIONS]
        insert_res = await collection.insert_one(doc)

        doc["_id"] = insert_res.inserted_id
        return _from_mongo_doc(doc)

    async def update_status(
        self,
        generation_id: str,
        status: str,
        updates: dict[str, Any] | None = None,
    ) -> GenerationResult | None:
        """Partially update a generation result's status and optional fields.

        Used by ``BackgroundTasks`` to update status from ``"processing"``
        to ``"success"`` or ``"failed"`` after the LLM call completes.

        Args:
            generation_id: The MongoDB ObjectId string of the result.
            status: New status value (``"processing"``, ``"success"``,
                ``"failed"``, ``"partial"``).
            updates: Optional additional fields to merge into the document.

        Returns:
            The updated result, or ``None`` if not found.
        """
        try:
            obj_id = ObjectId(generation_id)
        except (InvalidId, TypeError):
            return None

        db = get_database()
        collection = db[MONGO_COLLECTION_GENERATIONS]

        fields: dict[str, Any] = {"status": status}
        if updates:
            for k, v in updates.items():
                if k == "test_cases":
                    fields["test_cases"] = [
                        {
                            "id": tc.id,
                            "title": tc.title,
                            "objective": tc.objective,
                            "preconditions": list(tc.preconditions),
                            "steps": list(tc.steps),
                            "expected_result": tc.expected_result,
                            "node_refs": [str(r) for r in tc.node_refs],
                        }
                        for tc in v
                    ]
                elif k == "validation_errors":
                    fields["validation_errors"] = list(v)
                elif isinstance(v, datetime):
                    fields[k] = v.isoformat()
                elif isinstance(v, UUID):
                    fields[k] = str(v)
                else:
                    fields[k] = v

        doc = await collection.find_one_and_update(
            {"_id": obj_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return None
        return _from_mongo_doc(doc)
