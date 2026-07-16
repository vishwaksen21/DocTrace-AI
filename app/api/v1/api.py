"""API Router aggregating all version 1 resource endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    documents,
    generations,
    selections,
    versions,
)

api_router = APIRouter()

api_router.include_router(
    documents.router,
    prefix="/documents",
    tags=["Documents"],
)
api_router.include_router(
    versions.router,
    prefix="/versions",
    tags=["Versions"],
)
api_router.include_router(
    selections.router,
    prefix="/selections",
    tags=["Selections"],
)
api_router.include_router(
    generations.router,
    prefix="/generations",
    tags=["Generations"],
)
