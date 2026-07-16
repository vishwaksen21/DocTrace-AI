"""Domain layer package.

Contains pure Python domain objects — no framework dependencies, no database
imports, no HTTP concepts.

    enums.py       Controlled vocabularies (NodeType, VersionStatus, DiffStatus)
    entities.py    Domain entity dataclasses (Document, Version, Node, …)
    exceptions.py  Domain exception hierarchy

Design principles:
    - All domain classes are immutable dataclasses (frozen=True)
    - No SQLAlchemy, FastAPI, or Pydantic imports here
    - The domain layer is the innermost ring of Clean Architecture;
      all other layers depend on it, but it depends on nothing
"""
