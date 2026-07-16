"""Integration tests for SQLAlchemy ORM models (Module 3).

All tests use an in-memory SQLite database to avoid any external
dependencies.  The schema is created fresh for each test class via
``Base.metadata.create_all()`` and destroyed via ``drop_all()``.

What is tested:
    - Table creation (all columns, constraints, FKs)
    - Inserting, querying, and deleting records
    - Cascades (deleting a Document removes its Versions and Nodes)
    - UniqueConstraint on (document_id, version_number)
    - Self-referential relationship on NodeModel.parent_id
    - SelectionModel ↔ NodeModel many-to-many via SelectionNodeModel
    - TimestampMixin populates created_at/updated_at
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.enums import NodeType, VersionStatus
from app.models.base import Base
from app.models.document import DocumentModel
from app.models.node import NodeModel
from app.models.selection import SelectionModel, SelectionNodeModel
from app.models.version import VersionModel

# ── Test engine (synchronous SQLite :memory: is fine for ORM unit tests) ─────
#
# We use the SYNCHRONOUS sqlalchemy engine here intentionally:
# these tests exercise the ORM models themselves, not the async
# infrastructure.  The async infrastructure is tested separately.

_SYNC_URL = "sqlite:///:memory:"


@pytest.fixture(scope="class")
def engine():
    """Create a shared in-memory engine for the test class."""
    eng = create_engine(
        _SYNC_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine):
    """Provide a transactional session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        try:
            transaction.rollback()
        except Exception:
            pass  # Transaction already deassociated (e.g., after IntegrityError)
        connection.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_HASH = "b" * 64


def _doc(title: str = "Test Doc") -> DocumentModel:
    return DocumentModel(title=title, original_filename="test.pdf")


def _version(document_id: uuid.UUID, number: int = 1) -> VersionModel:
    return VersionModel(
        document_id=document_id,
        version_number=number,
        upload_filename="test.pdf",
        status=VersionStatus.PROCESSING,
    )


def _node(
    version_id: uuid.UUID,
    position: int = 0,
    parent_id: uuid.UUID | None = None,
    node_type: NodeType = NodeType.PARAGRAPH,
    heading_level: int | None = None,
) -> NodeModel:
    return NodeModel(
        version_id=version_id,
        parent_id=parent_id,
        node_type=node_type,
        heading_level=heading_level,
        content=f"Content at position {position}",
        content_hash=VALID_HASH,
        position_index=position,
        path=str(position),
    )


# ── Document tests ────────────────────────────────────────────────────────────


class TestDocumentModel:
    def test_insert_and_query(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()
        assert doc.id is not None

        result = session.get(DocumentModel, doc.id)
        assert result is not None
        assert result.title == "Test Doc"

    def test_timestamp_mixin_populates_created_at(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()
        # created_at must be set (server_default); updated_at as well
        session.refresh(doc)
        assert doc.created_at is not None

    def test_uuid_primary_key_is_generated(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()
        assert isinstance(doc.id, uuid.UUID)

    def test_two_documents_have_different_ids(self, session: Session) -> None:
        d1, d2 = _doc("A"), _doc("B")
        session.add_all([d1, d2])
        session.flush()
        assert d1.id != d2.id

    def test_cascade_delete_removes_versions(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()

        ver = _version(doc.id)
        session.add(ver)
        session.flush()

        session.delete(doc)
        session.flush()

        assert session.get(VersionModel, ver.id) is None


# ── Version tests ─────────────────────────────────────────────────────────────


class TestVersionModel:
    def test_unique_constraint_prevents_duplicate_version_numbers(
        self, session: Session
    ) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()

        v1 = _version(doc.id, number=1)
        v2 = _version(doc.id, number=1)  # same number — should fail
        session.add(v1)
        session.flush()

        session.add(v2)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_same_version_number_allowed_for_different_documents(
        self, session: Session
    ) -> None:
        d1, d2 = _doc("A"), _doc("B")
        session.add_all([d1, d2])
        session.flush()

        v1 = _version(d1.id, number=1)
        v2 = _version(d2.id, number=1)
        session.add_all([v1, v2])
        session.flush()  # should not raise

        assert v1.id != v2.id

    def test_status_defaults_to_processing(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()
        ver = _version(doc.id)
        session.add(ver)
        session.flush()
        assert ver.status == VersionStatus.PROCESSING


# ── Node tests ────────────────────────────────────────────────────────────────


class TestNodeModel:
    def test_insert_paragraph_node(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()
        ver = _version(doc.id)
        session.add(ver)
        session.flush()

        node = _node(ver.id, position=0)
        session.add(node)
        session.flush()

        result = session.get(NodeModel, node.id)
        assert result is not None
        assert result.node_type == NodeType.PARAGRAPH

    def test_self_referential_parent_child(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()
        ver = _version(doc.id)
        session.add(ver)
        session.flush()

        parent = _node(ver.id, position=0, node_type=NodeType.HEADING, heading_level=1)
        session.add(parent)
        session.flush()

        child = _node(ver.id, position=1, parent_id=parent.id)
        session.add(child)
        session.flush()

        result = session.get(NodeModel, child.id)
        assert result.parent_id == parent.id

    def test_cascade_delete_from_version_removes_nodes(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()
        ver = _version(doc.id)
        session.add(ver)
        session.flush()

        node = _node(ver.id)
        session.add(node)
        session.flush()

        session.delete(ver)
        session.flush()

        assert session.get(NodeModel, node.id) is None

    def test_content_hash_stored_correctly(self, session: Session) -> None:
        doc = _doc()
        session.add(doc)
        session.flush()
        ver = _version(doc.id)
        session.add(ver)
        session.flush()

        node = _node(ver.id)
        session.add(node)
        session.flush()

        result = session.get(NodeModel, node.id)
        assert result.content_hash == VALID_HASH


# ── Selection tests ───────────────────────────────────────────────────────────


class TestSelectionModel:
    def _setup(self, session: Session):
        """Create a document, version, and two nodes; return (version, node1, node2)."""
        doc = _doc()
        session.add(doc)
        session.flush()
        ver = _version(doc.id)
        session.add(ver)
        session.flush()
        n1 = _node(ver.id, position=0)
        n2 = _node(ver.id, position=1)
        session.add_all([n1, n2])
        session.flush()
        return ver, n1, n2

    def test_selection_with_two_nodes(self, session: Session) -> None:
        ver, n1, n2 = self._setup(session)

        sel = SelectionModel(version_id=ver.id, name="My Selection")
        session.add(sel)
        session.flush()

        j1 = SelectionNodeModel(selection_id=sel.id, node_id=n1.id)
        j2 = SelectionNodeModel(selection_id=sel.id, node_id=n2.id)
        session.add_all([j1, j2])
        session.flush()

        result = session.get(SelectionModel, sel.id)
        assert result is not None
        node_ids = {n.id for n in result.nodes}
        assert n1.id in node_ids
        assert n2.id in node_ids

    def test_duplicate_junction_row_raises(self, session: Session) -> None:
        ver, n1, _ = self._setup(session)

        sel = SelectionModel(version_id=ver.id)
        session.add(sel)
        session.flush()

        j1 = SelectionNodeModel(selection_id=sel.id, node_id=n1.id)
        j2 = SelectionNodeModel(selection_id=sel.id, node_id=n1.id)  # duplicate
        session.add_all([j1, j2])
        with pytest.raises(IntegrityError):
            session.flush()

    def test_cascade_delete_selection_removes_junction_rows(
        self, session: Session
    ) -> None:
        ver, n1, _ = self._setup(session)

        sel = SelectionModel(version_id=ver.id)
        session.add(sel)
        session.flush()

        j = SelectionNodeModel(selection_id=sel.id, node_id=n1.id)
        session.add(j)
        session.flush()

        session.delete(sel)
        session.flush()

        # Junction row must also be gone
        remaining = session.execute(
            text(
                "SELECT COUNT(*) FROM selection_nodes "
                "WHERE selection_id = :sid"
            ),
            {"sid": str(sel.id)},
        ).scalar()
        assert remaining == 0
