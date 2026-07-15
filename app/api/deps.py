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

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.config import get_settings as _get_settings
from app.infrastructure.database import get_session
from app.infrastructure.mongodb import get_database


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


__all__ = ["get_db", "get_mongo", "get_settings"]
