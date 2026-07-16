"""NodeModel — ORM representation of the ``nodes`` table."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import NodeType
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.version import VersionModel


class NodeModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persistence model for the ``nodes`` table.

    Each node represents one structural unit of a parsed PDF: a heading,
    paragraph, table, or list item.  Nodes form a tree via the self-
    referential ``parent_id`` column.

    Table: ``nodes``

    Indexes:
        - ``(version_id, position_index)`` — primary access pattern for
          retrieving nodes in document order for a given version
        - ``(version_id, content_hash)`` — O(1) hash lookup used by the
          diff engine to find matching nodes across versions
        - ``(version_id, parent_id)`` — efficient children queries for
          hierarchy reconstruction

    Note on ``content_hash``
        Stored as ``CHAR(64)`` (fixed-width) rather than ``VARCHAR(64)``:
        SQL engines can store and compare fixed-width strings more efficiently,
        and a SHA-256 hex digest is always exactly 64 characters.

    Note on ``path``
        Materialized path (e.g. ``"0"``, ``"0.2"``, ``"0.2.1"``) stored as
        a plain string.  Enables subtree queries with a single ``LIKE '0.2%'``
        predicate without recursive CTEs.  This is a practical trade-off
        for the expected document depth (< 6 levels).
    """

    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_version_position", "version_id", "position_index"),
        Index("ix_nodes_version_hash", "version_id", "content_hash"),
        Index("ix_nodes_version_parent", "version_id", "parent_id"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("versions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Parent version UUID.  Cascades delete.",
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        doc="Self-referential parent node UUID.  NULL = root node.",
    )
    node_type: Mapped[NodeType] = mapped_column(
        SAEnum(
            NodeType,
            name="nodetype",
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        doc="Structural type of this node.",
    )
    heading_level: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        default=None,
        doc="Heading depth 1-6 for HEADING nodes; NULL for all other types.",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Raw text content.  Tables stored in Markdown table format.",
    )
    content_hash: Mapped[str] = mapped_column(
        CHAR(64),
        nullable=False,
        doc="SHA-256 hex digest of normalized content.  Used for O(1) change detection.",
    )
    position_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Global 0-based ordering within the version.  Preserves document reading order.",
    )
    path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Materialized path (e.g. '0.2.1').  Enables subtree queries without recursion.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    version: Mapped[VersionModel] = relationship(
        "VersionModel",
        back_populates="nodes",
        lazy="select",
    )
    children: Mapped[list[NodeModel]] = relationship(
        "NodeModel",
        primaryjoin="NodeModel.parent_id == NodeModel.id",
        foreign_keys="NodeModel.parent_id",
        lazy="select",
        doc="Direct child nodes ordered by position_index.",
        order_by="NodeModel.position_index",
    )

    def __repr__(self) -> str:
        return (
            f"NodeModel(id={self.id!r}, "
            f"node_type={self.node_type!r}, "
            f"position_index={self.position_index!r}, "
            f"path={self.path!r})"
        )
