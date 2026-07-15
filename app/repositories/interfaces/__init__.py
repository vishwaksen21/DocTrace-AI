"""Repository interface contracts.

This package defines ``typing.Protocol`` classes that every repository
implementation must satisfy.  Implementations may use SQLAlchemy,
in-memory dicts, or any other backend — as long as they implement the
corresponding Protocol, they are accepted by the service layer.

Protocols vs ABCs
-----------------
We use ``Protocol`` (structural typing / duck typing) rather than ABCs:
    - No explicit inheritance required → simpler mock objects in tests
    - Type checkers verify structural compatibility at the call site
    - Swapping backends requires zero changes to existing implementations

Type annotations
----------------
Domain entity types (``Document``, ``Version``, ``Node``, ``Selection``)
are referenced via ``TYPE_CHECKING`` imports and ``from __future__ import
annotations``.  This means annotations are strings at runtime (PEP 563)
and do not cause ``ImportError`` until M3 provides the actual types.
"""
