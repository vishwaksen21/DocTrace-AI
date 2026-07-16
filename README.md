# DocTrace AI

AI-powered document tracing and QA test-case generation backend. It extracts logical structure from system specification PDFs, tracks structural changes across versions, and scopes LLM-driven test case generation based on user-selected nodes.

## Technical Architecture

DocTrace AI is built using **Clean Architecture** patterns:

- **Framework**: FastAPI (async ASGI)
- **Primary Relational DB**: SQLite (Development) / PostgreSQL (Production ready) via SQLAlchemy async engine with Alembic migrations.
- **Document Store**: MongoDB (Motor async driver) for storing rich generated test cases.
- **Cache**: Redis for API rate-limiting and token blacklisting.
- **Observability**: OpenTelemetry instrumentation (FastAPI, SQLAlchemy, HTTPX) exporting to Prometheus and OTLP collectors, combined with structured `structlog` logging.

### Codebase Layout

```
app/
├── api/             # API routes, error mapping, and dependencies
├── core/            # Config settings, logging, and global constants
├── domain/          # Pure entity models, enums, and domain exceptions
├── infrastructure/  # SQLAlchemy and MongoDB connections/indexes
├── llm/             # OpenRouter client wrapper and JSON validators
├── parser/          # PyMuPDF and pdfplumber extraction pipeline
├── repositories/    # Database repositories following protocol interfaces
├── services/        # Core business logic service layer
└── versioning/      # Position-anchored version matching & diff engines
```

## Quick Start

### Setup Environment
```bash
cp .env.example .env
```
Open `.env` and set your `OPENROUTER_API_KEY`.

### Run via Docker (Recommended)
To start the application, MongoDB, and Redis in local containers:
```bash
docker compose up --build
```
- API server: `http://127.0.0.1:8000`
- Interactive Swagger docs: `http://127.0.0.1:8000/docs`

### Run Natively (macOS)
If running directly on your host machine:

```bash
# Start background services
brew services start redis
brew services start mongodb-community@7.0

# Install package dependencies
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Launch Uvicorn dev server
uvicorn app.main:app --reload
```

## End-to-End Testing Flow

We have created an automated test script to run the full document lifecycle from PDF compilation to test case generation. Run it while your API server is running:

```bash
python scratch/test_flow.py
```

### Manual Testing with cURL

Alternatively, you can test the APIs step-by-step using a local PDF (like `spec.pdf`):

#### 1. Upload a PDF
```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -F "title=Spec Document" \
  -F "file=@spec.pdf"
```
*Saves document metadata and returns a `document_id` and initial `version_id`.*

#### 2. Check Version Status
```bash
curl http://127.0.0.1:8000/api/v1/documents/<doc_id>/versions
```
*Wait until `status` changes from `"processing"` to `"ready"`.*

#### 3. Fetch Parsed Nodes
```bash
curl http://127.0.0.1:8000/api/v1/versions/<version_id>/nodes
```
*Lists all headings, paragraphs, and list items extracted from the PDF.*

#### 4. Register a Node Selection
```bash
curl -X POST http://127.0.0.1:8000/api/v1/selections \
  -H "Content-Type: application/json" \
  -d '{
    "version_id": "<version_id>",
    "node_ids": ["<node_id_1>", "<node_id_2>"],
    "name": "Audit Scope"
  }'
```

#### 5. Trigger LLM Test Case Generation
```bash
curl -X POST http://127.0.0.1:8000/api/v1/selections/<selection_id>/generate
```
*Queues the generation and returns a BSON Hex ObjectId under `id`.*

#### 6. Retrieve Generated Test Cases
```bash
curl http://127.0.0.1:8000/api/v1/generations/<generation_id>
```

## Development and Verification

### Run Test Suite
```bash
pytest
```
*Runs all 320+ unit and integration tests using transactionally isolated SQL databases and mocked LLM interfaces.*

### Code Quality Checking
```bash
# Run strict type checking
mypy app --strict

# Run linter checks
ruff check app
```
