# ADR 0009: Selection & Generation API — Range Selection + Background QA Generation

## Status
Accepted

## Context
Users need to:
1. Select a range of nodes (by UUID) for test case generation
2. Trigger async LLM generation
3. Poll for results

## Decision
**Selection = named set of node UUIDs** scoped to a single version.
**Generation = background task** storing results in MongoDB.

### Selection Model
```python
# app/domain/entities.py
@dataclass(frozen=True)
class Selection:
    id: UUID
    version_id: UUID
    node_ids: tuple[UUID, ...]  # Ordered, unique, same version
    name: str | None
    created_at: datetime
```

### Validation Rules
- `node_ids` non-empty
- All nodes belong to `version_id`
- Duplicate UUIDs rejected
- Cross-version selection → `CrossVersionSelectionError`

### API Endpoints
```
POST   /api/v1/selections                    Create selection
GET    /api/v1/selections/{id}               Get selection + resolved nodes
POST   /api/v1/selections/{id}/generate      Trigger QA generation (202)
GET    /api/v1/selections/{id}/generations   List generations (paginated)
GET    /api/v1/generations/{id}              Get generation result
```

### Generation Flow
```
1. POST /selections/{id}/generate
   │
   ▼
2. GenerationService.trigger_generation()
   ├── Create GenerationResult (status=PROCESSING) in MongoDB
   ├── Return 202 with GenerationResponse
   │
   ▼ (BackgroundTasks)
3. Background worker:
   ├── Fetch selection nodes (with content)
   ├── Build prompt (prompts.py)
   ├── Call LLM with structured output (TestCaseSuite)
   ├── On success: update status=COMPLETED, store test_cases
   ├── On failure: update status=FAILED, store error_message
   │
   ▼
4. Client polls GET /generations/{id} until status != PROCESSING
```

### Structured Output (`app/llm/prompts.py`)
```python
class TestCase(BaseModel):
    id: str
    title: str
    description: str
    steps: list[str]
    expected_result: str
    priority: Literal["high", "medium", "low"]
    tags: list[str]

class TestCaseSuite(BaseModel):
    test_cases: list[TestCase]
    summary: str
```

### Prompt Template
```
You are a QA engineer. Generate test cases for the following document sections.

Document: {document_title}
Version: {version_number}
Selected Sections:
{node_contents}

Requirements:
- Cover functional, edge case, negative, and integration scenarios
- Prioritize high-risk areas
- Output valid JSON matching TestCaseSuite schema
```

### Error Handling
| Scenario | HTTP | Error Code |
|----------|------|------------|
| Selection not found | 404 | SelectionNotFound |
| Version not ready | 409 | VersionNotReady |
| Empty selection | 400 | EmptySelection |
| LLM rate limit | 503 | LLMRateLimitError |
| LLM timeout | 504 | LLMTimeoutError |
| Invalid JSON from LLM | 502 | LLMProviderError |

## Consequences
### Positive
- Selections reusable across generations
- Background processing → responsive API
- MongoDB stores large LLM responses efficiently
- Structured output enables UI rendering

### Negative
- Eventual consistency (polling required)
- MongoDB required for generation endpoints
- No streaming support (single response)

## Configuration
```bash
# LLM
OPENROUTER_API_KEY=sk-or-...
LLM_MODEL=google/gemini-2.5-flash
LLM_TEMPERATURE=0.0
LLM_MAX_TOKENS=8192

# Background tasks
GENERATION_TIMEOUT_SECONDS=120
```

## Validation
- 12 API tests for selections/generations
- 8 service tests (validation, error paths)
- 6 LLM client tests (mocked OpenRouter)
- Integration test: full flow upload → select → generate → poll