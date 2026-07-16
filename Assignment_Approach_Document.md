# Assignment Approach Document

This document details the engineering decisions, architecture, and algorithms implemented in DocTrace AI. The system solves a core challenge in software QA engineering: extracting system requirements from unstructured documentation, tracking structural updates across versions, and automatically generating or updating test suites to align with changes.

## System Architecture

DocTrace AI follows **Clean Architecture** principles to separate business logic from external frameworks, databases, and third-party APIs:

- **Domain Layer (`app/domain`)**: Defines core entities (Document, Version, Node, Selection, QATestCase, Generation) and business rules. This layer contains zero external library dependencies (pure Python).
- **Service Layer (`app/services`)**: Orchestrates use cases and application workflow logic. It is database-agnostic, interacting with data stores via abstract repository interfaces.
- **Repository Layer (`app/repositories`)**: Implements concrete data storage patterns (SQLAlchemy for relational data, Motor/MongoDB for unstructured LLM outputs).
- **API Layer (`app/api`)**: FastAPI controllers, schemas (Pydantic), and global exceptions that expose operations over REST.

### Component Diagram

```
[ API Layer (FastAPI) ]
         │
         ▼
[ Service Layer (Orchestration) ] ───► [ Versioning/Diff Engine ]
         │
         ├───► [ Repositories (Interfaces) ]
         │               ▲
         │               │ (Dependency Inversion)
         │               │
         │     ┌─────────┴─────────┐
         │     │                   │
         ▼     ▼                   ▼
  [ SQLite / Postgres ]      [ MongoDB ]      [ Redis (Cache) ]
```

## Database and Caching Strategy

The data architecture is split to match the access patterns of relational structured data vs. dynamic LLM-generated test cases:

- **SQL Store (SQLite/PostgreSQL)**: Handles the relational structure of documents, versions, nodes (hierarchical headings, paragraphs), and user selections. Schema updates are managed via Alembic migrations.
- **NoSQL Store (MongoDB)**: Used to store generated test cases. Since test cases can have dynamic formats depending on the context of the source node, MongoDB's flexible BSON document structure is ideal.
- **Cache (Redis)**: Serves as the session-scoped cache for API rate-limiting and a token blacklist store for JWT session invalidation.

## Core Modules Implementation

### PDF Parsing Pipeline
The parser converts raw PDF bytes into a logical document tree:
- **Structure Extraction**: `PyMuPDF` parses paragraphs, list items, and headings. Heading fonts and size ratios are used to identify hierarchical heading levels.
- **Table Parsing**: `pdfplumber` acts as a fallback parser specifically for grid-based tables, converting raw table cells into markdown tables to preserve content structure.
- **Hierarchical Node Builder**: Reconstructs the document into a tree where each node has a parent-child relationship, path key (e.g. `0.1.2`), content hash, and position index.

### Position-Anchored Version Diffing
Instead of traditional text diffing (like `git diff`), DocTrace AI implements a custom tree matching algorithm:
- **Anchors**: Relies on hierarchical paths (`0.1`, `0.1.0`) and content hashes to map equivalent nodes between Version $N$ and Version $N+1$.
- **Diff Types**: Identifies additions, deletions, text updates, and structural node moves (e.g. moving a section under a different parent).

### Scoped Test Case Generation
QA engineers can select a subset of document nodes (a Selection) to scope generation:
- **Context Injection**: The prompt builder extracts the text context of selected nodes and their structural ancestors.
- **OpenRouter LLM Interface**: Outgoing completions are sent to Gemini via OpenRouter.
- **Validation and List Coercion**: A validation parser verifies that the LLM response strictly matches the target JSON schema using Pydantic. It automatically coerces common LLM formatting anomalies (like returning a single string for list attributes like `preconditions` or `steps`) into single-element lists, preventing schema validation failures.

## Verification and Testing Strategy

The test suite runs 321 automated tests to guarantee functional correctness:

- **Transaction Isolation**: Test setups use a function-scoped database engine. It rolls back the SQL database transaction after every single unit test, preventing state leakage across test cases.
- **Mocking**: External services (Motor/MongoDB and OpenRouter HTTP calls) are isolated using strict mock client interfaces.
- **Lint and Types**: Type verification is enforced via strict mypy configurations (`--strict`), and code formatting conforms to Ruff linting standards.

## Observability and Hardening

- **Observability**: OpenTelemetry spans trace requests across the API, database queries (via SQLAlchemy sync engine wrappers), and LLM client calls. Metrics are exposed via a Prometheus endpoint.
- **Resilience**: The OpenRouter client integrates `Tenacity` retries with exponential backoff on HTTP timeouts.
- **Circuit Breaker**: A software circuit breaker wraps external LLM APIs. If the third-party provider fails consistently, it trips, returning structured fallback errors to prevent thread starvation.
