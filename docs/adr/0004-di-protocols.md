# ADR 0004: Dependency Injection via FastAPI Depends + Protocols

## Status
Accepted

## Context
Need a DI mechanism that:
- Works natively with FastAPI
- Enables easy testing with fakes/mocks
- Keeps business logic decoupled from framework

## Decision
Use **FastAPI's `Depends`** with **Protocol interfaces** for all service/repository dependencies.

### Pattern
```python
# Repository protocol (app/repositories/interfaces/node.py)
class NodeRepositoryProtocol(Protocol):
    async def get_by_id(self, node_id: UUID) -> Node | None: ...
    async def list_by_version(self, version_id: UUID, ...) -> tuple[list[Node], int]: ...

# Concrete implementation (app/repositories/node.py)
class NodeRepository(NodeRepositoryProtocol):
    def __init__(self, session: AsyncSession): ...

# Dependency provider (app/api/deps.py)
def get_node_repository(
    session: AsyncSession = Depends(get_db_session),
) -> NodeRepositoryProtocol:
    return NodeRepository(session)

# Route usage (app/api/v1/endpoints/selections.py)
async def get_selection(
    selection_id: UUID,
    sel_service: SelectionService = Depends(get_selection_service),
    node_repo: NodeRepositoryProtocol = Depends(get_node_repository),
) -> SelectionWithNodesResponse: ...
```

### Testing
```python
# tests/conftest.py
@pytest.fixture
def override_deps(app: FastAPI):
    app.dependency_overrides[get_node_repository] = lambda: FakeNodeRepository()
    yield
    app.dependency_overrides.clear()
```

## Consequences
### Positive
- Native FastAPI integration (no external DI library)
- Type-safe with `Protocol` — mypy validates implementations
- Zero boilerplate for production wiring
- Tests remain fast (in-memory fakes, no DB)

### Negative
- `Depends` only works in FastAPI route handlers
- Service constructors must accept dependencies as parameters
- Circular dependency risk if not careful (mitigated by layer rules)

## Conformance
- All 10 repository interfaces use this pattern
- All 5 services use this pattern
- 100% of API endpoints use `Depends` for dependencies