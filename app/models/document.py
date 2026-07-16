"""DocumentModel — ORM representation of the ``documents`` table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.version import VersionModel


class DocumentModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persistence model for the ``documents`` table.

    A document is the stable aggregate that persists across multiple PDF
    uploads (versions).  Only metadata lives here; parsed content is in
    ``versions`` → ``nodes``.

    Table: ``documents``
    """

    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Human-readable document title.",
    )
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Filename of the first uploaded PDF; preserved for auditability.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    versions: Mapped[list[VersionModel]] = relationship(
        "VersionModel",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="VersionModel.version_number",
        lazy="select",
        doc="All versions of this document, ordered by version_number ascending.",
    )

    def __repr__(self) -> str:
        return (
            f"DocumentModel(id={self.id!r}, title={self.title!r})"
        )
