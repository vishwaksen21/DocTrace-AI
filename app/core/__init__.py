"""Core application package.

Contains pure infrastructure concerns that have no framework dependencies
beyond Python's standard library and pydantic:

    - config.py    Application settings (pydantic-settings)
    - logging.py   Structured logging (structlog)
    - constants.py Application-wide fixed values

Business logic must never be placed in this package.
"""
