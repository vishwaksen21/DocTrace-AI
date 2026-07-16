# ADR 0001: Clean Architecture with Strict Layer Separation

## Status
Accepted

## Context
The project needs a maintainable, testable architecture that separates business logic from framework concerns. The team wants to avoid framework lock-in and enable unit testing without external dependencies.

## Decision
Adopt **Clean Architecture** with the following layers:

```
app/
├── api/              # FastAPI routes, dependencies (framework-specific)
├── core/             # Pure configuration, logging, constants (no framework deps)
├── domain/           # Entities, enums, exceptions (pure Python, no deps)
├── infrastructure/   # Database (SQLAlchemy), MongoDB (Motor), logging shim
├── llm/              # LLM abstraction (Protocol + value types)
├── parser/           # PDF parsing logic (PyMuPDF, pdfplumber)
├── repositories/     # Data access implementations
│   └── interfaces/   # Repository Protocols (dependency inversion)
├── services/         # Business logic, orchestration
├── versioning/       # Diff/matching algorithms
├── schemas/          # Pydantic request/response models
├── main.py           # App factory + lifespan
└── config.py         # Compat shim → app.core.config
```

### Layer Rules
1. **Inner layers never depend on outer layers** — dependencies point inward
2. **Domain layer** has zero external dependencies (pure Python)
3. **Application layer** (services, repositories) depends only on domain
4. **Infrastructure layer** implements repository interfaces
5. **API layer** depends on services via FastAPI `Depends` with protocols

## Consequences
### Positive
- High testability: domain/services tested with in-memory fakes
- Framework independence: could swap FastAPI for another framework
- Clear separation of concerns
- Easy to onboard new developers

### Negative
- More boilerplate (interfaces, dependency injection)
- Slight indirection when navigating code

## Implementation Notes
- Repository protocols defined in `app/repositories/interfaces/`
- FastAPI `Depends` injects concrete implementations at runtime
- Tests override dependencies via `app.dependency_overrides`