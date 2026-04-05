"""
Legacy unified memory system entrypoint (deprecated).

The upstream YAAM "UnifiedMemorySystem" depended on autonomous engines and
additional storage adapters that are intentionally excluded from this repository
per RFC-005. The WinterSim orchestrator should use direct, explicit read/write
operations via `memory.yaam_facade.YAAMFacade` instead.
"""

from __future__ import annotations

from .yaam_facade import YAAMFacade, get_facade, set_facade

__all__ = ["YAAMFacade", "get_facade", "set_facade"]

