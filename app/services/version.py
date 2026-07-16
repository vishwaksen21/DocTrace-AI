"""Version service layer.

Orchestrates Version-related use cases, including PDF parsing and diffing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from fastapi import BackgroundTasks

from app.domain.entities import Node, Version
from app.domain.enums import VersionStatus
from app.domain.exceptions import (
    BusinessValidationError,
    DocumentNotFoundError,
    NodeNotFoundError,
    VersionDiffError,
    VersionNotFoundError,
    VersionNotReadyError,
)
from app.infrastructure.database import get_session
from app.repositories import SqlAlchemyNodeRepository, SqlAlchemyVersionRepository

if TYPE_CHECKING:
    from app.domain.entities import NodeDiff
    from app.repositories.interfaces.document import DocumentRepositoryProtocol
    from app.repositories.interfaces.node import NodeRepositoryProtocol
    from app.repositories.interfaces.version import VersionRepositoryProtocol

logger = structlog.get_logger(__name__)


async def parse_and_persist_version_task(version_id: UUID, pdf_bytes: bytes) -> None:
    """Background task to parse a PDF upload and persist its node tree.

    Executed out-of-band by FastAPI's BackgroundTasks.  Gets a fresh database
    session to guarantee transaction isolation.

    Args:
        version_id: The UUID of the Version record being processed.
        pdf_bytes: The raw bytes of the uploaded PDF file.
    """
    logger.info("Starting background PDF parsing task", version_id=str(version_id))
    async with get_session() as session:
        version_repo = SqlAlchemyVersionRepository(session)
        node_repo = SqlAlchemyNodeRepository(session)

        try:
            # 1. Run the five-pass PDF parser pipeline
            from app.parser.pdf_parser import parse_pdf
            parsed_nodes = await parse_pdf(pdf_bytes)

            # 2. Map intermediate ParsedNodes to Node domain entities
            node_ids = {p.position_index: uuid4() for p in parsed_nodes}
            domain_nodes = []
            for p in parsed_nodes:
                parent_uuid = (
                    node_ids[p.parent_position_index]
                    if p.parent_position_index is not None
                    else None
                )
                node_uuid = node_ids[p.position_index]

                node = Node(
                    id=node_uuid,
                    version_id=version_id,
                    node_type=p.node_type,
                    content=p.content,
                    content_hash=p.content_hash,
                    position_index=p.position_index,
                    path=p.path,
                    created_at=datetime.now(tz=UTC),
                    parent_id=parent_uuid,
                    heading_level=p.heading_level,
                )
                domain_nodes.append(node)

            # 3. Bulk save nodes to the database
            if domain_nodes:
                await node_repo.bulk_create(domain_nodes)

            # 4. Mark version as READY
            await version_repo.update_status(version_id, VersionStatus.READY)
            await session.commit()
            logger.info(
                "PDF parsing completed successfully",
                version_id=str(version_id),
                total_nodes=len(domain_nodes),
            )

        except Exception as exc:
            # Handle parsing failures gracefully: flag the version as failed
            logger.error(
                "PDF parsing encountered an error",
                version_id=str(version_id),
                error=str(exc),
            )
            try:
                await version_repo.update_status(
                    version_id, VersionStatus.FAILED, error_message=str(exc)
                )
                await session.commit()
            except Exception as inner_exc:
                logger.error(
                    "Failed to record version processing failure",
                    version_id=str(version_id),
                    error=str(inner_exc),
                )


class VersionService:
    """Service class for managing Versions and node diffs."""

    def __init__(
        self,
        version_repo: VersionRepositoryProtocol,
        node_repo: NodeRepositoryProtocol,
        doc_repo: DocumentRepositoryProtocol,
    ) -> None:
        """Initialize the VersionService with repositories."""
        self.version_repo = version_repo
        self.node_repo = node_repo
        self.doc_repo = doc_repo

    async def get_version(self, version_id: UUID) -> Version | None:
        """Retrieve a version by ID.

        Args:
            version_id: The UUID of the version.
        """
        return await self.version_repo.get_by_id(version_id)

    async def get_version_or_raise(self, version_id: UUID) -> Version:
        """Retrieve a version or raise VersionNotFoundError.

        Args:
            version_id: The UUID of the version.
        """
        ver = await self.version_repo.get_by_id(version_id)
        if ver is None:
            raise VersionNotFoundError(version_id)
        return ver

    async def list_versions(
        self,
        document_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Version], int]:
        """List all versions for a document.

        Args:
            document_id: The parent document UUID.
            offset: Skip offset.
            limit: Return limit.
        """
        if not await self.doc_repo.exists(document_id):
            raise DocumentNotFoundError(document_id)
        return await self.version_repo.list_for_document(document_id, offset, limit)

    async def list_nodes(
        self,
        version_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Node], int]:
        """List all nodes for a version.

        Args:
            version_id: The version UUID.
            offset: Skip offset.
            limit: Return limit.
        """
        ver = await self.get_version_or_raise(version_id)
        if ver.status != VersionStatus.READY:
            raise VersionNotReadyError(version_id, str(ver.status))
        return await self.node_repo.list_for_version(version_id, offset, limit)

    async def get_node_children(self, version_id: UUID, parent_id: UUID) -> list[Node]:
        """List child nodes for a parent heading node.

        Args:
            version_id: The version UUID.
            parent_id: The parent node UUID.
        """
        ver = await self.get_version_or_raise(version_id)
        if ver.status != VersionStatus.READY:
            raise VersionNotReadyError(version_id, str(ver.status))

        parent_node = await self.node_repo.get_by_id(parent_id)
        if parent_node is None:
            raise NodeNotFoundError(parent_id)
        if parent_node.version_id != version_id:
            raise BusinessValidationError(
                f"Node '{parent_id}' does not belong to version '{version_id}'."
            )

        return await self.node_repo.get_children(parent_id)

    async def create_version(
        self,
        document_id: UUID,
        upload_filename: str,
        pdf_bytes: bytes,
        background_tasks: BackgroundTasks,
    ) -> Version:
        """Upload and start processing a new version of a document.

        Generates version number atomically and queues the parsing job.

        Args:
            document_id: The parent document UUID.
            upload_filename: Original PDF filename.
            pdf_bytes: Raw bytes of the uploaded PDF file.
            background_tasks: Starlette background tasks orchestrator.
        """
        if not await self.doc_repo.exists(document_id):
            raise DocumentNotFoundError(document_id)

        # Generate next version sequence number atomically using document-level locks
        version_number = await self.version_repo.get_next_version_number(document_id)

        version_id = uuid4()
        ver = Version(
            id=version_id,
            document_id=document_id,
            version_number=version_number,
            upload_filename=upload_filename,
            status=VersionStatus.PROCESSING,
            created_at=datetime.now(tz=UTC),
        )
        saved = await self.version_repo.create(ver)
        if hasattr(self.version_repo, "session"):
            await self.version_repo.session.commit()

        # Queue parsing job to run in background thread pool/task
        background_tasks.add_task(
            parse_and_persist_version_task,
            version_id=version_id,
            pdf_bytes=pdf_bytes,
        )

        return saved

    async def compare_versions(
        self,
        new_version_id: UUID,
        old_version_id: UUID | None = None,
    ) -> list[NodeDiff]:
        """Compute the structural diff between two document versions.

        Args:
            new_version_id: The newer version's UUID.
            old_version_id: The older comparison version's UUID. If None,
                defaults to the version immediately preceding new_version.
        """
        new_ver = await self.get_version_or_raise(new_version_id)
        if new_ver.status != VersionStatus.READY:
            raise VersionNotReadyError(new_version_id, str(new_ver.status))

        if old_version_id is None:
            old_ver = await self.version_repo.get_previous_version(
                new_ver.document_id, new_ver.version_number
            )
        else:
            old_ver = await self.get_version_or_raise(old_version_id)
            if old_ver.status != VersionStatus.READY:
                raise VersionNotReadyError(old_version_id, str(old_ver.status))
            if old_ver.document_id != new_ver.document_id:
                raise VersionDiffError(
                    old_version_id,
                    new_version_id,
                    "Cannot diff versions belonging to different documents.",
                )

        new_nodes = await self.node_repo.get_nodes_for_diff(new_version_id)
        old_nodes = []
        if old_ver is not None:
            old_nodes = await self.node_repo.get_nodes_for_diff(old_ver.id)

        from app.versioning import diff_versions

        try:
            return diff_versions(old_nodes, new_nodes)
        except ValueError as exc:
            raise VersionDiffError(
                old_ver.id if old_ver else uuid4(),
                new_version_id,
                str(exc),
            ) from exc
