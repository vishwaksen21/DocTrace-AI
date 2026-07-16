# DocTrace AI

AI-powered document tracing and QA test-case generation backend.

> **M14 Documentation** — [Architecture Decision Records](adr/README.md) | [OpenAPI Spec](http://localhost:8000/openapi.json) | [Swagger UI](http://localhost:8000/docs)

## Quick Start

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY

docker compose up
# API available at http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

## Architecture Overview

DocTrace AI follows **Clean Architecture** with strict layer separation:

```
app/
├── api/              # FastAPI dependencies, routes (M11+)
├── core/             # Pure configuration, logging, constants (no framework deps)
├── domain/           # Entities, enums, exceptions (pure Python)
├── infrastructure/   # Database (SQLAlchemy), MongoDB (Motor), logging shim
├── llm/              # LLM abstraction (Protocol + value types)
├── parser/           # PDF parsing (PyMuPDF + pdfplumber)
├── repositories/
│   └── interfaces/   # Repository Protocols (dependency inversion)
├── services/         # Business logic, orchestration
├── versioning/       # Diff/matching algorithms
├── schemas/          # Pydantic request/response models
├── main.py           # App factory + lifespan
└── config.py         # Compat shim → app.core.config
```

### Key Design Decisions

See [Architecture Decision Records](adr/README.md) for detailed rationale.

| Concern | Approach | ADR |
|---------|----------|-----|
| **Architecture** | Clean Architecture with strict layer separation | [0001](adr/0001-clean-architecture.md) |
| **Database** | SQLite (dev) → PostgreSQL (prod) via `DATABASE_URL` | [0002](adr/0002-database-strategy.md) |
| **LLM** | Provider-agnostic via `LLMClientProtocol` | [0003](adr/0003-llm-protocol.md) |
| **DI** | FastAPI `Depends` with Protocol interfaces | [0004](adr/0004-di-fastapi-protocols.md) |
| **PDF Parsing** | PyMuPDF + pdfplumber hybrid pipeline | [0007](adr/0007-pdf-parsing.md) |
| **Version Diff** | Position-anchored matching with content hashing | [0008](adr/0008-version-diff.md) |
| **Observability** | OpenTelemetry + Prometheus + Structured Logging | [0006](adr/0006-observability.md) |
| **Logging** | `structlog` — JSON in prod, colorized console in dev; correlation IDs | — |

## Configuration

All settings via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | `development \| staging \| production` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/doctrace.db` | SQLAlchemy async URL |
| `MONGODB_URL` | `mongodb://localhost:27017` | Motor connection string |
| `OPENROUTER_API_KEY` | *(required for LLM)* | LLM provider API key |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | LLM API base URL |
| `LLM_MODEL` | `google/gemini-2.5-flash` | Model identifier |
| `DB_POOL_SIZE` | `5` | PostgreSQL connection pool size |
| `DB_MAX_OVERFLOW` | `10` | PostgreSQL max overflow connections |
| `DB_POOL_TIMEOUT` | `30.0` | Pool checkout timeout (seconds) |
| `DB_POOL_RECYCLE` | `3600` | Connection recycle interval (seconds) |
| `DB_POOL_PRE_PING` | `true` | Enable connection liveness check |

### LLM Provider Switching

Change two variables — zero code changes:

```bash
# OpenRouter (default)
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=google/gemini-2.5-flash

# OpenAI
OPENROUTER_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Groq
OPENROUTER_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-70b-versatile
```

## Running Locally (without Docker)

```bash
# Install dependencies
pip install -e ".[dev]"

# Start MongoDB (optional - LLM endpoints return 503 without it)
brew services start mongodb-community  # macOS
# or: docker run -d -p 27017:27017 mongo:7

# Run API
uvicorn app.main:app --reload
```

## API Endpoints (M1–M2)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check — returns `{"status": "healthy"}` |
| `GET` | `/health/ready` | Readiness check — verifies DB + MongoDB connectivity |

V1 API routes (documents, versions, nodes, selections, generations) are implemented in **M11+**.

## Development

### Commands

```bash
# Run tests
pytest

# Type check
mypy app --strict

# Lint
ruff check app

# Format
ruff format app
```

### Project Structure (M1–M2)

```
.
├── app/
│   ├── api/
│   │   └── deps.py           # FastAPI dependency injection
│   ├── core/
│   │   ├── config.py         # Pydantic Settings
│   │   ├── constants.py      # Compile-time constants
│   │   └── logging.py        # Structlog configuration
│   ├── infrastructure/
│   │   ├── database.py       # SQLAlchemy async engine + session
│   │   ├── mongodb.py        # Motor client + indexes
│   │   └── logging.py        # Compatibility shim
│   ├── llm/
│   │   └── base.py           # LLMClientProtocol + exceptions
│   ├── repositories/
│   │   └── interfaces/       # Protocol definitions
│   ├── main.py               # FastAPI app + lifespan
│   └── config.py             # Compat shim → app.core.config
├── tests/
│   ├── test_config.py
│   └── test_infrastructure/
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── alembic.ini               # (M3+)
```

## Testing

```bash
# All tests (unit, no external services required)
pytest

# With coverage
pytest --cov=app --cov-report=term-missing
```

Tests use in-memory SQLite and mocked MongoDB — no external services needed.

## Docker

### Development

```bash
docker compose up
# Source mounted for hot-reload; SQLite persisted in ./data
```

### Production

```bash
# Build
docker build -t doctrace-ai .

# Run (set ENVIRONMENT=production, provide PostgreSQL + MongoDB)
docker run -d \
  -e ENVIRONMENT=production \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@host/db \
  -e MONGODB_URL=mongodb://mongo:27017 \
  -e OPENROUTER_API_KEY=sk-or-... \
  -p 8000:8000 \
  doctrace-ai
```

The Dockerfile runs as non-root user `appuser` (UID 1000).

## Security Notes

- **CORS**: Wildcard origins (`*`) allowed only in `development`; credentials disabled
- **Health endpoint**: `/health` exposes minimal info; `/health/ready` returns service status for k8s probes
- **Secrets**: Never commit `.env` — it's in `.gitignore`
- **API keys**: Logged only as presence/absence warnings at startup

## Roadmap

| Module | Focus | Status |
|--------|-------|--------|
| M3 | Domain entities + SQLAlchemy models + Alembic migrations | ✅ Done |
| M4 | PDF upload, parsing (PyMuPDF), versioning | ✅ Done |
| M5 | Node extraction, heading hierarchy, content hashing | ✅ Done |
| M6 | Version diff engine (position-anchored matching) | ✅ Done |
| M7 | Range selection API | ✅ Done |
| M8 | Document service layer | ✅ Done |
| M9 | Selection service layer | ✅ Done |
| M10 | OpenRouter LLM client implementation | ✅ Done |
| M11 | Generation API + background tasks | ✅ Done |
| M12 | API hardening (validation, errors, rate limits) | ✅ Done |
| M13 | Observability (metrics, tracing) | ✅ Done |
| M14 | Documentation (OpenAPI, ADRs) | ✅ Done |

## License

MIT