from __future__ import annotations

from typing import Any, Literal


class KnowledgeStoreManager:
    def __init__(
        self,
        vector_store: Any | None = None,
        graph_store: Any | None = None,
    ) -> None:
        """Initialize with injected store clients.

        The upstream YAAM implementation used specialized storage adapters under
        `src.storage.*`. Those are intentionally excluded from this repository
        per RFC-005, so this manager is now a lightweight dispatcher around
        injected clients (typically Qdrant for L3 and Typesense for L4).
        """
        self.vector_store = vector_store
        self.graph_store = graph_store

    def add(self, store_type: Literal["vector"], documents: list[dict[str, Any]]) -> Any:
        """
        Adds documents to the specified store.
        Note: Graph store additions are typically done via query.
        """
        if store_type == "vector":
            if self.vector_store is None:
                raise RuntimeError("Vector store is not configured.")
            add_documents = getattr(self.vector_store, "add_documents", None)
            if not callable(add_documents):
                raise RuntimeError("Vector store client does not support add_documents().")
            return add_documents(documents)

        raise ValueError(f"Adding documents to '{store_type}' is not supported via this method.")

    def query(
        self,
        store_type: Literal["vector", "graph"],
        query_text: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Routes a query to the appropriate knowledge store with a unified interface.

        Args:
            store_type: The type of store to query ('vector' or 'graph').
            query_text: The primary query content (e.g., text for semantic/full-text search, or a Cypher query for graph).
            top_k: The number of results to return.
            filters: A structured dictionary for filtering results, which will be translated.

        Returns:
            A list of result dictionaries.
        """
        if store_type == "vector":
            if self.vector_store is None:
                raise RuntimeError("Vector store is not configured.")
            query_similar = getattr(self.vector_store, "query_similar", None)
            if not callable(query_similar):
                raise RuntimeError("Vector store client does not support query_similar().")

            normalized_filters = self._normalize_vector_filters(filters) if filters else None
            return query_similar(query_text=query_text, top_k=top_k, filters=normalized_filters)

        elif store_type == "graph":
            if self.graph_store is None:
                raise RuntimeError("Graph store is not configured.")
            query = getattr(self.graph_store, "query", None)
            if not callable(query):
                raise RuntimeError("Graph store client does not support query().")
            return query(cypher_query=query_text, params=filters)

        else:
            raise ValueError(f"Unknown store_type: {store_type}")

    def _normalize_vector_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        """Normalize vector-store filters into an adapter-agnostic dictionary."""
        return dict(filters)
