"""Generation service layer.

Orchestrates QA test-case generation use cases and coordinates background LLM completions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from fastapi import BackgroundTasks

from app.domain.entities import GenerationResult
from app.domain.enums import GenerationStatus
from app.domain.exceptions import (
    GenerationNotFoundError,
    SelectionNotFoundError,
)
from app.infrastructure.database import get_session

if TYPE_CHECKING:
    from app.llm.base import LLMClientProtocol
    from app.repositories.interfaces.selection import (
        GenerationRepositoryProtocol,
        SelectionRepositoryProtocol,
    )

logger = structlog.get_logger(__name__)


async def generate_qa_cases_task(
    generation_id: str,
    selection_id: UUID,
    llm_client: LLMClientProtocol,
) -> None:
    """Background task to fetch selection nodes, call the LLM, and persist results.

    Executed out-of-band by FastAPI's BackgroundTasks.

    Args:
        generation_id: The MongoDB ObjectId string of the GenerationResult record.
        selection_id: The UUID of the Selection representing the chosen QA scope.
        llm_client: The LLMClient instance to perform the completion.
    """
    logger.info("Starting background QA test-case generation", generation_id=generation_id)

    from app.repositories.generation import MongoGenerationRepository

    generation_repo = MongoGenerationRepository()

    # 1. Fetch selection and its nodes in a short-lived SQL session
    async with get_session() as session:
        from app.repositories.node import SqlAlchemyNodeRepository
        from app.repositories.selection import SqlAlchemySelectionRepository

        selection_repo = SqlAlchemySelectionRepository(session)
        node_repo = SqlAlchemyNodeRepository(session)

        selection = await selection_repo.get_by_id(selection_id)
        if selection is None:
            logger.error("Selection not found for QA generation", selection_id=str(selection_id))
            await generation_repo.update_status(
                generation_id,
                GenerationStatus.FAILED,
                {"validation_errors": ["Parent selection not found."]},
            )
            return

        # Eagerly fetch the full node entities for context
        nodes = []
        for nid in selection.node_ids:
            node = await node_repo.get_by_id(nid)
            if node is not None:
                nodes.append(node)

    # 2. Build prompts and messages
    from app.llm.base import LLMMessage
    from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt

    user_content = build_user_prompt(nodes)
    messages = [
        LLMMessage(role="system", content=SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]

    t0 = datetime.now(tz=UTC)
    try:
        from app.core.constants import LLM_DEFAULT_TEMPERATURE, LLM_JSON_RESPONSE_FORMAT

        # Call the LLM provider (JSON format constrained)
        response = await llm_client.complete(
            messages=messages,
            temperature=LLM_DEFAULT_TEMPERATURE,
            response_format=LLM_JSON_RESPONSE_FORMAT,
            max_tokens=2048,
        )
        duration_ms = (datetime.now(tz=UTC) - t0).total_seconds() * 1000.0

        # 3. Parse and validate structured output
        from app.llm.response_validator import validate_llm_json

        valid_cases, errors = validate_llm_json(response.content)

        # 4. Compute status depending on validation errors
        if not valid_cases:
            status = GenerationStatus.FAILED
            errors.append("No valid test cases could be parsed from LLM response.")
        elif errors:
            status = GenerationStatus.PARTIAL
        else:
            status = GenerationStatus.SUCCESS

        await generation_repo.update_status(
            generation_id=generation_id,
            status=status,
            updates={
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "test_cases": valid_cases,
                "validation_errors": errors,
                "raw_response": response.raw_response,
                "duration_ms": duration_ms,
            },
        )
        logger.info(
            "QA test-case generation completed",
            generation_id=generation_id,
            status=str(status),
            total_cases=len(valid_cases),
            validation_errors=len(errors),
        )

    except Exception as exc:
        duration_ms = (datetime.now(tz=UTC) - t0).total_seconds() * 1000.0
        logger.error(
            "QA test-case generation failed with exception",
            generation_id=generation_id,
            error=str(exc),
        )
        await generation_repo.update_status(
            generation_id=generation_id,
            status=GenerationStatus.FAILED,
            updates={
                "validation_errors": [f"LLM completion call failed: {exc}"],
                "duration_ms": duration_ms,
            },
        )


class GenerationService:
    """Service class for coordinating QA test-case generations."""

    def __init__(
        self,
        generation_repo: GenerationRepositoryProtocol,
        selection_repo: SelectionRepositoryProtocol,
        llm_client: LLMClientProtocol,
    ) -> None:
        """Initialize the GenerationService.

        Args:
            generation_repo: Concrete GenerationRepositoryProtocol (MongoDB).
            selection_repo: Concrete SelectionRepositoryProtocol.
            llm_client: Concrete LLMClientProtocol.
        """
        self.generation_repo = generation_repo
        self.selection_repo = selection_repo
        self.llm_client = llm_client

    async def get_generation(self, generation_id: str) -> GenerationResult | None:
        """Retrieve a GenerationResult by MongoDB ObjectId string.

        Args:
            generation_id: BSON ObjectId hex string.
        """
        return await self.generation_repo.get_by_id(generation_id)

    async def get_generation_or_raise(self, generation_id: str) -> GenerationResult:
        """Retrieve a GenerationResult or raise GenerationNotFoundError.

        Args:
            generation_id: BSON ObjectId hex string.
        """
        res = await self.generation_repo.get_by_id(generation_id)
        if res is None:
            raise GenerationNotFoundError(generation_id)
        return res

    async def list_generations(
        self,
        selection_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[GenerationResult], int]:
        """List paginated generation results for a specific selection.

        Args:
            selection_id: Target Selection UUID.
            offset: Page skip count.
            limit: Return count.
        """
        if not await self.selection_repo.exists(selection_id):
            raise SelectionNotFoundError(selection_id)
        return await self.generation_repo.list_for_selection(selection_id, offset, limit)

    async def trigger_generation(
        self,
        selection_id: UUID,
        background_tasks: BackgroundTasks,
    ) -> GenerationResult:
        """Trigger QA generation for a selection.

        Saves an initial PROCESSING generation record and schedules the LLM job.

        Args:
            selection_id: Target Selection UUID.
            background_tasks: Starlette background tasks orchestrator.
        """
        # 1. Fetch parent selection
        selection = await self.selection_repo.get_by_id(selection_id)
        if selection is None:
            raise SelectionNotFoundError(selection_id)

        # 2. Create initial PROCESSING record in MongoDB
        initial_result = GenerationResult(
            selection_id=selection.id,
            document_id=uuid4(),  # temporary, populated on complete if needed or left as context
            version_id=selection.version_id,
            model=self.llm_client.model,
            prompt_tokens=0,
            completion_tokens=0,
            status=GenerationStatus.PROCESSING,
            raw_response="",
            test_cases=(),
            validation_errors=(),
            created_at=datetime.now(tz=UTC),
            duration_ms=0.0,
        )

        saved = await self.generation_repo.create(initial_result)
        assert saved.id is not None  # populated by Mongo driver

        # 3. Schedule the completion job in background thread pool/task
        background_tasks.add_task(
            generate_qa_cases_task,
            generation_id=saved.id,
            selection_id=selection.id,
            llm_client=self.llm_client,
        )

        return saved
