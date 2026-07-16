"""QA generations query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_generation_service
from app.schemas import GenerationResponse
from app.services import GenerationService

router = APIRouter()


@router.get(
    "/{generation_id}",
    response_model=GenerationResponse,
    summary="Get generation result",
    description=(
        "Retrieve LLM QA test case generation status and results "
        "by MongoDB ObjectId hex string."
    ),
)
async def get_generation(
    generation_id: str,
    gen_service: GenerationService = Depends(get_generation_service),
) -> GenerationResponse:
    # Service automatically raises GenerationNotFoundError if missing, mapped to 404
    res = await gen_service.get_generation_or_raise(generation_id)
    return GenerationResponse.model_validate(res)
