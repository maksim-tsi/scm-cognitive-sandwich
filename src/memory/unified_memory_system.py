"""
Legacy hybrid memory system (deprecated).

The original upstream implementation bundled:
- L1/L2/L3/L4 tiers
- autonomous promotion/consolidation/distillation engines
- Neo4j graph storage
- LLM-dependent embedding/query plumbing

Per RFC-005 and the WinterSim infrastructure audit, this repository intentionally
excludes the missing `engines/` and `schemas/` modules and does not use Neo4j.

For the orchestrator, prefer the explicit, deterministic, direct connectors in:
`memory.yaam_facade.YAAMFacade`.
"""

from __future__ import annotations

from .yaam_facade import YAAMFacade, get_facade, set_facade

__all__ = ["YAAMFacade", "get_facade", "set_facade"]

