"""SelectionModel and SelectionNodeModel — ORM for selections and junction table."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.node import NodeModel
    from app.models.version import VersionModel


class SelectionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persistence model for the ``selections`` table.

    A selection is a named, ordered set of nodes chosen for LLM QA generation.
    The actual node membership is stored in the ``selection_nodes`` junction
    table to keep the relationship queryable.

    Table: ``selections``
    """

    __tablename__ = "selections"

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="The version all selected nodes belong to.",
    )
    name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        default=None,
        doc="Optional user-provided label for this selection.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    version: Mapped[VersionModel] = relationship(
        "VersionModel",
        back_populates="selections",
        lazy="select",
    )
    nodes: Mapped[list[NodeModel]] = relationship(
        "NodeModel",
        secondary="selection_nodes",
        lazy="select",
        doc="Selected nodes via the selection_nodes junction table.",
    )

    def __repr__(self) -> str:
        return (
            f"SelectionModel(id={self.id!r}, "
            f"version_id={self.version_id!r}, "
            f"name={self.name!r})"
        )


class SelectionNodeModel(Base):
    """Junction table associating selections with their chosen nodes.

    Table: ``selection_nodes``

    Primary key: ``(selection_id, node_id)`` composite — prevents a node
    from appearing twice in the same selection and allows efficient existence
    checks without a surrogate key.

    Both foreign keys cascade-delete so that removing a selection or node
    automatically removes the junction rows.  We explicitly do NOT cascade
    delete nodes when a selection is removed (the node belongs to the version,
    not the selection).
    """

    __tablename__ = "selection_nodes"
    __table_args__ = (
        UniqueConstraint(
            "selection_id",
            "node_id",
            name="uq_selection_nodes_selection_node",
        ),
    )

    selection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("selections.id", ondelete="CASCADE"),
        primary_key=True,
        doc="FK to selections.id; cascades delete when the selection is removed.",
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        primary_key=True,
        doc="FK to nodes.id; cascades delete when the node is removed.",
    )

    def __repr__(self) -> str:
        return (
            f"SelectionNodeModel("
            f"selection_id={self.selection_id!r}, "
            f"node_id={self.node_id!r})"
        )
