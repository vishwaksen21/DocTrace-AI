"""FastAPI dependency injection factories.

All injectable dependencies for route handlers are declared here.
Using FastAPI's ``Depends`` system ensures:
    - Dependencies are created lazily per request
    - Cleanup code (session close, connection return) runs reliably
    - Tests can override any dependency with ``app.dependency_overrides``

Dependency hierarchy (current modules, will grow through M8-M11):

    Infrastructure
    ├── get_db()       → AsyncSession (SQLAlchemy)
    └── get_mongo()    → AsyncIOMotorDatabase (Motor)

    Configuration
    └── get_settings() → Settings (re-exported for convenience)

    Future (M8-M11)
    ├── get_document_repository()  → DocumentRepositoryProtocol
    ├── get_version_repository()   → VersionRepositoryProtocol
    ├── get_node_repository()      → NodeRepositoryProtocol
    ├── get_selection_repository() → SelectionRepositoryProtocol
    ├── get_generation_repository()→ GenerationRepositoryProtocol
    ├── get_document_service()     → DocumentService
    ├── get_generation_service()   → GenerationService
    └── get_llm_client()           → LLMClientProtocol

Override pattern for tests::

    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_db

    def override_db():
        yield test_session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.config import get_settings as _get_settings
from app.infrastructure.database import get_session
from app.infrastructure.mongodb import get_database
from app.llm import LLMClientProtocol, OpenRouterClient
from app.repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyNodeRepository,
    SqlAlchemySelectionRepository,
    SqlAlchemyVersionRepository,
)
from app.repositories.generation import MongoGenerationRepository
from app.repositories.interfaces import (
    DocumentRepositoryProtocol,
    GenerationRepositoryProtocol,
    NodeRepositoryProtocol,
    SelectionRepositoryProtocol,
    VersionRepositoryProtocol,
)
from app.services import (
    DocumentService,
    GenerationService,
    SelectionService,
    VersionService,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a SQLAlchemy ``AsyncSession`` scoped to a single HTTP request.

    The session is automatically rolled back when an unhandled exception
    propagates.  Service-layer code is responsible for calling
    ``session.commit()`` after successful writes.

    Inject into route handlers::

        @router.post("/documents")
        async def create(db: AsyncSession = Depends(get_db)) -> ...:
            ...
    """
    async with get_session() as session:
        yield session


def get_mongo() -> AsyncIOMotorDatabase:  # type: ignore[type-arg]
    """Provide the Motor MongoDB database handle.

    Motor manages its own internal connection pool; this dependency
    simply returns the handle initialised at startup.

    Inject into route handlers::

        @router.post("/generate")
        async def generate(mongo: AsyncIOMotorDatabase = Depends(get_mongo)) -> ...:
            ...
    """
    return get_database()


def get_settings() -> Settings:
    """Provide the application settings singleton.

    Re-exported here so route handlers only need to import from
    ``app.api.deps``, reducing coupling to ``app.core.config``.

    Inject into route handlers::

        @router.get("/health")
        async def health(settings: Settings = Depends(get_settings)) -> ...:
            return {"version": settings.app_version}
    """
    return _get_settings()


# ── Repositories ──────────────────────────────────────────────────────────────


def get_document_repository(
    session: AsyncSession = Depends(get_db),
) -> DocumentRepositoryProtocol:
    """Provide a Document repository implementation."""
    return SqlAlchemyDocumentRepository(session)


def get_version_repository(
    session: AsyncSession = Depends(get_db),
) -> VersionRepositoryProtocol:
    """Provide a Version repository implementation."""
    return SqlAlchemyVersionRepository(session)


def get_node_repository(
    session: AsyncSession = Depends(get_db),
) -> NodeRepositoryProtocol:
    """Provide a Node repository implementation."""
    return SqlAlchemyNodeRepository(session)


def get_selection_repository(
    session: AsyncSession = Depends(get_db),
) -> SelectionRepositoryProtocol:
    """Provide a Selection repository implementation."""
    return SqlAlchemySelectionRepository(session)


def get_generation_repository() -> GenerationRepositoryProtocol:
    """Provide a Generation repository implementation."""
    return MongoGenerationRepository()


# ── LLM Client ────────────────────────────────────────────────────────────────


def get_llm_client(settings: Settings = Depends(get_settings)) -> LLMClientProtocol:
    """Provide a concrete LLM client instance."""
    return OpenRouterClient(settings)


# ── Services ──────────────────────────────────────────────────────────────────


def get_document_service(
    doc_repo: DocumentRepositoryProtocol = Depends(get_document_repository),
    version_repo: VersionRepositoryProtocol = Depends(get_version_repository),
) -> DocumentService:
    """Provide a DocumentService instance."""
    return DocumentService(doc_repo, version_repo)


def get_version_service(
    version_repo: VersionRepositoryProtocol = Depends(get_version_repository),
    node_repo: NodeRepositoryProtocol = Depends(get_node_repository),
    doc_repo: DocumentRepositoryProtocol = Depends(get_document_repository),
) -> VersionService:
    """Provide a VersionService instance."""
    return VersionService(version_repo, node_repo, doc_repo)


def get_selection_service(
    selection_repo: SelectionRepositoryProtocol = Depends(get_selection_repository),
    version_repo: VersionRepositoryProtocol = Depends(get_version_repository),
    node_repo: NodeRepositoryProtocol = Depends(get_node_repository),
) -> SelectionService:
    """Provide a SelectionService instance."""
    return SelectionService(selection_repo, version_repo, node_repo)


def get_generation_service(
    generation_repo: GenerationRepositoryProtocol = Depends(get_generation_repository),
    selection_repo: SelectionRepositoryProtocol = Depends(get_selection_repository),
    llm_client: LLMClientProtocol = Depends(get_llm_client),
) -> GenerationService:
    """Provide a GenerationService instance."""
    return GenerationService(generation_repo, selection_repo, llm_client)


__all__ = [
    "get_db",
    "get_document_repository",
    "get_document_service",
    "get_generation_repository",
    "get_generation_service",
    "get_llm_client",
    "get_mongo",
    "get_node_repository",
    "get_selection_repository",
    "get_selection_service",
    "get_settings",
    "get_version_repository",
    "get_version_service",
]
