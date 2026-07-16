"""Node selections management endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.deps import (
    get_generation_service,
    get_node_repository,
    get_selection_service,
)
from app.repositories.interfaces.node import NodeRepositoryProtocol
from app.schemas import (
    GenerationResponse,
    NodeResponse,
    PaginatedResponse,
    SelectionCreate,
    SelectionResponse,
)
from app.schemas.selection import SelectionWithNodesResponse
from app.services import GenerationService, SelectionService

router = APIRouter()


@router.post(
    "",
    response_model=SelectionResponse,
    status_code=201,
    summary="Create node selection",
    description="Store a unique selection scope of node UUIDs for test case generation.",
)
async def create_selection(
    payload: SelectionCreate,
    sel_service: SelectionService = Depends(get_selection_service),
) -> SelectionResponse:
    sel = await sel_service.create_selection(
        version_id=payload.version_id,
        node_ids=payload.node_ids,
        name=payload.name,
    )
    return SelectionResponse.model_validate(sel)


@router.get(
    "/{selection_id}",
    response_model=SelectionWithNodesResponse,
    summary="Get selection details",
    description="Retrieve selection details along with complete node details.",
)
async def get_selection(
    selection_id: UUID,
    sel_service: SelectionService = Depends(get_selection_service),
    node_repo: NodeRepositoryProtocol = Depends(get_node_repository),
) -> SelectionWithNodesResponse:
    sel = await sel_service.get_selection_or_raise(selection_id)

    # Resolve full node details
    nodes = []
    for node_id in sel.node_ids:
        node = await node_repo.get_by_id(node_id)
        if node is not None:
            nodes.append(NodeResponse.model_validate(node))

    return SelectionWithNodesResponse(
        id=sel.id,
        version_id=sel.version_id,
        node_ids=list(sel.node_ids),
        name=sel.name,
        created_at=sel.created_at,
        nodes=nodes,
    )


@router.post(
    "/{selection_id}/generate",
    response_model=GenerationResponse,
    status_code=202,
    summary="Trigger QA generation",
    description=(
        "Queue an LLM completion job to generate QA test cases "
        "for selected nodes. Returns 202 Accepted."
    ),
)
async def trigger_qa_generation(
    selection_id: UUID,
    background_tasks: BackgroundTasks,
    gen_service: GenerationService = Depends(get_generation_service),
) -> GenerationResponse:
    res = await gen_service.trigger_generation(
        selection_id=selection_id,
        background_tasks=background_tasks,
    )
    return GenerationResponse.model_validate(res)


@router.get(
    "/{selection_id}/generations",
    response_model=PaginatedResponse[GenerationResponse],
    summary="List QA generations",
    description="Retrieve a paginated page of QA test case generation results for a selection.",
)
async def list_selection_generations(
    selection_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    gen_service: GenerationService = Depends(get_generation_service),
) -> PaginatedResponse[GenerationResponse]:
    items, total = await gen_service.list_generations(
        selection_id=selection_id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(
        items=[GenerationResponse.model_validate(x) for x in items],
        total=total,
        offset=offset,
        limit=limit,
    )
