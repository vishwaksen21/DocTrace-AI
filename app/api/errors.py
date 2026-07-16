"""Global API exception mapping for DomainError taxonomy."""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.constants import HEADER_REQUEST_ID
from app.domain.exceptions import (
    BusinessValidationError,
    ConflictError,
    DomainError,
    NotFoundError,
    ProcessingError,
)

logger = structlog.get_logger(__name__)


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Standardized handler for all business and domain errors.

    Maps exception taxonomy to correct HTTP status codes and responds
    with standard ErrorResponse body formats.
    """
    # Narrow to DomainError since we only register for DomainError subclasses
    domain_exc: DomainError = exc  # type: ignore[assignment]
    if isinstance(exc, NotFoundError):
        status_code = 404
        error_code = "NotFound"
    elif isinstance(exc, ConflictError):
        status_code = 409
        error_code = "Conflict"
    elif isinstance(exc, BusinessValidationError):
        status_code = 422
        error_code = "ValidationError"
    elif isinstance(exc, ProcessingError):
        status_code = 500
        error_code = "ProcessingError"
    else:
        status_code = 500
        error_code = "InternalServerError"

    request_id = request.headers.get(HEADER_REQUEST_ID, "")

    logger.warning(
        "Domain error handled",
        error=error_code,
        message=domain_exc.message,
        details=domain_exc.details,
        status_code=status_code,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "error": error_code,
            "message": domain_exc.message,
            "details": domain_exc.details,
            "request_id": request_id,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register DomainError exception handler on the FastAPI app instance."""
    app.add_exception_handler(DomainError, domain_error_handler)
