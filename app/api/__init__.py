"""API layer package.

Contains:
    deps.py    FastAPI dependency factories (sessions, services, settings)
    v1/        Route handlers (added in M11)
    errors.py  Global exception handlers (added in M11)

All route handlers must delegate work to the service layer.
Business logic must never appear in route handlers.
"""
