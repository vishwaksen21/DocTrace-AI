"""VersionModel — ORM representation of the ``versions`` table."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import VersionStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import DocumentModel
    from app.models.node import NodeModel
    from app.models.selection import SelectionModel


class VersionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persistence model for the ``versions`` table.

    A version is an immutable record of a single PDF upload.  Its ``status``
    field is the only column that changes post-INSERT — updated by the
    background parsing task as it progresses from PROCESSING → READY / FAILED.

    Table: ``versions``

    Unique constraint: ``(document_id, version_number)`` ensures no two
    versions of the same document share a version number, even under
    concurrent uploads.
    """

    __tablename__ = "versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_versions_document_id_version_number",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent document UUID.  Cascades delete to versions.",
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="1-based sequential version number, scoped per document.",
    )
    upload_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Original filename of the PDF uploaded for this version.",
    )
    status: Mapped[VersionStatus] = mapped_column(
        SAEnum(
            VersionStatus,
            name="versionstatus",
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        default=VersionStatus.PROCESSING,
        doc="Parse lifecycle status.  Updated by background task.",
    )
    error_message: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
        default=None,
        doc="Set when status=FAILED; brief technical description of the parse error.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    document: Mapped[DocumentModel] = relationship(
        "DocumentModel",
        back_populates="versions",
        lazy="select",
    )
    nodes: Mapped[list[NodeModel]] = relationship(
        "NodeModel",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="NodeModel.position_index",
        lazy="select",
        doc="Parsed nodes for this version, ordered by position.",
    )
    selections: Mapped[list[SelectionModel]] = relationship(
        "SelectionModel",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"VersionModel(id={self.id!r}, "
            f"document_id={self.document_id!r}, "
            f"version_number={self.version_number!r}, "
            f"status={self.status!r})"
        )
