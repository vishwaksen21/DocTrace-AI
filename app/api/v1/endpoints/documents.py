"""Document and document version endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
)

from app.api.deps import get_document_service, get_version_service
from app.schemas import (
    DocumentResponse,
    DocumentUploadResponse,
    PaginatedResponse,
    VersionResponse,
)
from app.services import DocumentService, VersionService

router = APIRouter()


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=201,
    summary="Upload new document",
    description="Create a document entry and queue its first version (Version 1) for parsing.",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    title: str = Form(..., description="Document title"),
    file: UploadFile = File(..., description="Source PDF file"),
    doc_service: DocumentService = Depends(get_document_service),
    ver_service: VersionService = Depends(get_version_service),
) -> DocumentUploadResponse:
    # 1. Create document
    doc = await doc_service.create_document(
        title=title,
        original_filename=file.filename or "uploaded.pdf",
    )

    # 2. Read raw PDF file bytes
    pdf_bytes = await file.read()

    # 3. Create initial version and queue parsing task
    version = await ver_service.create_version(
        document_id=doc.id,
        upload_filename=file.filename or "uploaded.pdf",
        pdf_bytes=pdf_bytes,
        background_tasks=background_tasks,
    )

    return DocumentUploadResponse(
        document=DocumentResponse.model_validate(doc),
        version=VersionResponse.model_validate(version),
    )


@router.get(
    "",
    response_model=PaginatedResponse[DocumentResponse],
    summary="List documents",
    description="Retrieve a paginated page of documents.",
)
async def list_documents(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    doc_service: DocumentService = Depends(get_document_service),
) -> PaginatedResponse[DocumentResponse]:
    items, total = await doc_service.list_documents(offset=offset, limit=limit)
    return PaginatedResponse(
        items=[DocumentResponse.model_validate(x) for x in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document",
    description="Retrieve a document's details by ID.",
)
async def get_document(
    document_id: UUID,
    doc_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    # Service automatically raises DocumentNotFoundError if missing, mapped to 404
    doc = await doc_service.get_document(document_id)
    if doc is None:
        from app.domain.exceptions import DocumentNotFoundError
        raise DocumentNotFoundError(document_id)
    return DocumentResponse.model_validate(doc)


@router.post(
    "/{document_id}/versions",
    response_model=VersionResponse,
    status_code=202,
    summary="Upload document version",
    description="Upload a new PDF version for an existing document. Returns 202 Accepted.",
)
async def upload_version(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="New PDF file version"),
    ver_service: VersionService = Depends(get_version_service),
) -> VersionResponse:
    pdf_bytes = await file.read()
    version = await ver_service.create_version(
        document_id=document_id,
        upload_filename=file.filename or "uploaded.pdf",
        pdf_bytes=pdf_bytes,
        background_tasks=background_tasks,
    )
    return VersionResponse.model_validate(version)


@router.get(
    "/{document_id}/versions",
    response_model=PaginatedResponse[VersionResponse],
    summary="List document versions",
    description="Retrieve a paginated list of versions associated with a document.",
)
async def list_versions(
    document_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    ver_service: VersionService = Depends(get_version_service),
) -> PaginatedResponse[VersionResponse]:
    items, total = await ver_service.list_versions(
        document_id=document_id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(
        items=[VersionResponse.model_validate(x) for x in items],
        total=total,
        offset=offset,
        limit=limit,
    )
