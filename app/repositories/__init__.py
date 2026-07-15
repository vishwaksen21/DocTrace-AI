"""Repository layer package.

Contains:
    interfaces/    Protocol-based contracts each repository must satisfy
    (M8)           SQLAlchemy implementations will be added in Module 8

Design rationale
----------------
Repositories follow the Repository Pattern: they are the single gateway
between the domain/service layer and the persistence layer.  No SQL or
MongoDB query code appears outside this package.

Each repository implementation depends *only* on its interface Protocol,
not on a concrete class.  This makes services testable with simple
in-memory stubs and allows swapping persistence backends without changing
any business logic.
"""
