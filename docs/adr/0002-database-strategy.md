# ADR 0002: SQLite (Dev) → PostgreSQL (Prod) via DATABASE_URL

## Status
Accepted

## Context
Need a database strategy that works for local development (zero-config) and production (PostgreSQL). The team wants to avoid maintaining separate code paths.

## Decision
Use **SQLAlchemy async engine** with a single `DATABASE_URL` environment variable:

| Environment | DATABASE_URL |
|-------------|--------------|
| Development | `sqlite+aiosqlite:///./data/doctrace.db` |
| Production  | `postgresql+asyncpg://user:pass@host/db` |

### Implementation
- `app/infrastructure/database.py`:
  - `_build_engine()` detects dialect from URL
  - SQLite: enables `pool_pre_ping`, disables pool (uses `NullPool`)
  - PostgreSQL: configures pool size, overflow, timeout, recycle via env vars
- Alembic migrations work for both dialects (tested with SQLite in CI)
- Models use dialect-agnostic types (`UUID`, `Text`, `DateTime`, `JSON`)

### Dialect-Specific Handling
```python
# In database.py
if "sqlite" in url:
    connect_args = {"check_same_thread": False}
    poolclass = NullPool
else:
    connect_args = {}
    poolclass = AsyncAdaptedQueuePool
```

## Consequences
### Positive
- Zero-config local development
- Single migration path
- No code changes between environments
- CI uses same SQLite as local dev

### Negative
- SQLite lacks some PostgreSQL features (e.g., `JSONB` ops, advisory locks)
- Must test PostgreSQL-specific queries in staging
- Alembic autogenerate may need manual tweaks for dialect differences

## Validation
- All 321 tests run against in-memory SQLite
- Production Docker image validates PostgreSQL connection at startup