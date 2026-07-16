# ADR 0008: Version Diff Engine — Position-Anchored Matching

## Status
Accepted

## Context
Need to compare document versions and detect:
- Added nodes
- Deleted nodes
- Modified nodes (content changed)
- Moved nodes (same content, different position)

## Decision
**Position-anchored matching** with content hash as primary key, position index as tiebreaker.

### Algorithm (`app/versioning/matcher.py`, `app/versioning/differ.py`)

```
OLD VERSION (v1)          NEW VERSION (v2)
┌─────────────────┐       ┌─────────────────┐
│ Node A (hash:1) │       │ Node A (hash:1) │  pos 0 → 0  UNCHANGED
│ Node B (hash:2) │       │ Node C (hash:3) │  pos 1 → -  DELETED
│ Node C (hash:3) │       │ Node B (hash:2) │  pos 2 → 1  MOVED
└─────────────────┘       │ Node D (hash:4) │  -    → 2  ADDED
                          └─────────────────┘
```

### Matching Rules
1. **Exact match**: Same `content_hash` AND same `position_index` → `UNCHANGED`
2. **Moved**: Same `content_hash`, different `position_index` within `tolerance` → `MOVED`
3. **Modified**: Same `position_index`, different `content_hash` → `MODIFIED`
4. **Added**: Hash not in old version → `ADDED`
5. **Deleted**: Hash not in new version → `DELETED`

### Tolerance
- Default: `tolerance=2` (allow ±2 position shift for MOVED)
- Configurable per-diff call
- `tolerance=0` → strict position matching

### Implementation
```python
# matcher.py
class NodeMatcher:
    def __init__(self, old_nodes: list[Node], new_nodes: list[Node], tolerance: int = 2):
        self.old_by_hash = group_by_hash(old_nodes)
        self.new_by_hash = group_by_hash(new_nodes)
        self.tolerance = tolerance

    def find_best_match(self, new_node: Node) -> MatchResult | None:
        candidates = self.old_by_hash.get(new_node.content_hash, [])
        # Prefer same position
        for c in candidates:
            if c.position_index == new_node.position_index:
                return MatchResult(c, DiffStatus.UNCHANGED)
        # Within tolerance
        for c in candidates:
            if abs(c.position_index - new_node.position_index) <= self.tolerance:
                return MatchResult(c, DiffStatus.MOVED)
        return None
```

```python
# differ.py
def diff_versions(old: list[Node], new: list[Node], tolerance: int = 2) -> list[NodeDiff]:
    matcher = NodeMatcher(old, new, tolerance)
    consumed = set()
    diffs = []

    # Pass 1: Match new → old
    for new_node in new:
        match = matcher.find_best_match(new_node)
        if match:
            consumed.add(match.old_node.id)
            diffs.append(NodeDiff(
                node=new_node,
                status=match.status,
                old_position_index=match.old_node.position_index,
                new_position_index=new_node.position_index,
            ))
        else:
            diffs.append(NodeDiff(node=new_node, status=DiffStatus.ADDED))

    # Pass 2: Unconsumed old → DELETED
    for old_node in old:
        if old_node.id not in consumed:
            diffs.append(NodeDiff(
                node=old_node,
                status=DiffStatus.DELETED,
                old_position_index=old_node.position_index,
            ))

    return diffs
```

### Output (`app/schemas/version.py`)
```python
class NodeDiffResponse(BaseModel):
    node_id: UUID
    old_node_id: UUID | None
    new_node_id: UUID | None
    status: DiffStatus  # UNCHANGED, ADDED, DELETED, MODIFIED, MOVED
    content_changed: bool
    old_path: str | None
    new_path: str | None
    old_position_index: int | None
    new_position_index: int | None
```

## Consequences
### Positive
- O(n) matching via hash index
- Handles reordering gracefully
- Position index enables "moved" detection
- Tolerance parameter adapts to editing patterns

### Negative
- Hash collision risk (SHA-256 → negligible)
- Duplicate content (same hash) at different positions → first match wins
- Tolerance tuning required per document type

## Configuration
```python
# app/core/constants.py
DEFAULT_DIFF_TOLERANCE = 2
```

## API
```python
# POST /api/v1/versions/{version_id}/diff?compare_to_version_id=...
# Returns: list[NodeDiffResponse]
```

## Validation
- 28 diff/matcher unit tests
- Scenarios: identical, added, deleted, modified, moved, mixed
- Edge cases: duplicates, tolerance boundaries, empty versions
- Golden master tests with known PDFs