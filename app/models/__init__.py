"""SQLAlchemy ORM models package.

Contains:
    base.py       DeclarativeBase, TimestampMixin, UUID primary-key helper
    document.py   DocumentModel
    version.py    VersionModel
    node.py       NodeModel
    selection.py  SelectionModel, SelectionNodeModel (junction)

Design principles:
    - Models are *not* domain entities; they are persistence representations
    - Domain entities live in ``app/domain/entities.py``
    - Mapping between ORM models and domain entities is done in repositories
    - This separation allows the domain to remain framework-free

Registering models with Alembic:
    Import all model modules in ``alembic/env.py`` so Alembic's autogenerate
    can detect all tables via ``Base.metadata``.
"""
