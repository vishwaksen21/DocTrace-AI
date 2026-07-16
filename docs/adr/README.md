# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records documenting significant design decisions for DocTrace AI.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-clean-architecture.md) | Clean Architecture with Strict Layer Separation | Accepted | 2026-07-16 |
| [0002](0002-database-strategy.md) | Database Strategy — SQLite (Dev) → PostgreSQL (Prod) | Accepted | 2026-07-16 |
| [0003](0003-llm-abstraction.md) | LLM Abstraction — Provider-Agnostic via Protocol | Accepted | 2026-07-16 |
| [0004](0004-di-protocols.md) | Dependency Injection via FastAPI Depends + Protocols | Accepted | 2026-07-16 |
| [0005](0005-pdf-parsing.md) | PDF Parsing Pipeline — PyMuPDF + Hierarchy Builder | Accepted | 2026-07-16 |
| [0006](0006-observability.md) | Observability — OpenTelemetry + Prometheus + Structured Logging | Accepted | 2026-07-16 |
| [0007](0007-version-diff.md) | Version Diff Engine — Position-Anchored Matching | Accepted | 2026-07-16 |
| [0008](0008-selection-generation.md) | Selection & Generation API — Range Selection + Background QA | Accepted | 2026-07-16 |

## Contributing

When making a significant architectural decision:

1. Create a new ADR file: `NNNN-short-title.md`
2. Use the template below
3. Add entry to this index
4. Submit via PR

### ADR Template

```markdown
# ADR NNNN: Short Title

## Status
[Proposed | Accepted | Superseded | Rejected]

## Context
What problem are we solving? What constraints exist?

## Decision
What did we decide? Include code snippets, diagrams, config.

## Consequences
### Positive
- Benefit 1
- Benefit 2

### Negative
- Trade-off 1
- Trade-off 2

## Implementation Notes
- Key files
- Configuration
- Testing approach
```