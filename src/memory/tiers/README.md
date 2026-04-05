# Memory Tiers

Implementation of the 4-tier memory architecture.

## Tier Hierarchy

```
L1 (Active Context)     → Short-term, session-scoped
    ↓ Promotion
L2 (Working Memory)     → Fact-based, CIAR-scored
    ↓ Consolidation  
L3 (Episodic Memory)    → Episode clusters with embeddings
    ↓ Distillation
L4 (Semantic Memory)    → Synthesized knowledge documents
```

## Files

| File | Tier | Storage Backend |
|------|------|-----------------|
| `base_tier.py` | Abstract base | - |
| `active_context_tier.py` | L1 | Redis |
| `working_memory_tier.py` | L2 | PostgreSQL |
| `episodic_memory_tier.py` | L3 | Qdrant + Neo4j |
| `semantic_memory_tier.py` | L4 | Typesense + Neo4j |

## Common Interface

All tiers implement:
- `store(data)` - Store data in the tier
- `retrieve(session_id, query)` - Retrieve data
- `query(filters, limit)` - Query with filters
- `health_check()` - Check tier health

## Telemetry

Each tier accepts an optional `telemetry_stream` parameter for Glass Box observability:

```python
tier = WorkingMemoryTier(
    postgres_adapter=pg,
    telemetry_stream=producer,
)
```
