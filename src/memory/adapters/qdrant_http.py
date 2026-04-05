from __future__ import annotations

import httpx


class QdrantHttpAdapter:
    def __init__(self, *, base_url: str, api_key: str | None = None) -> None:
        resolved = base_url.strip().rstrip("/")
        if not resolved:
            raise ValueError("Qdrant base_url must be a non-empty URL")
        self._base_url = resolved
        self._api_key = (api_key or "").strip() or None

    def list_collections(self) -> list[str]:
        url = f"{self._base_url}/collections"
        headers: dict[str, str] = {}
        if self._api_key:
            headers["api-key"] = self._api_key

        with httpx.Client() as client:
            response = client.get(url, headers=headers, timeout=15.0)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover
                detail = response.text.strip()
                raise httpx.HTTPStatusError(
                    f"{exc}. Body: {detail[:500]}",
                    request=exc.request,
                    response=exc.response,
                ) from exc
            data = response.json()

        result = data.get("result") if isinstance(data, dict) else None
        collections = result.get("collections") if isinstance(result, dict) else None
        names: list[str] = []
        if isinstance(collections, list):
            for item in collections:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    names.append(item["name"])
        return names

    def ensure_collection(
        self,
        *,
        collection: str,
        vector_size: int,
        distance: str = "Cosine",
    ) -> None:
        """Create the collection if missing (idempotent)."""
        resolved_collection = collection.strip()
        if not resolved_collection:
            raise ValueError("collection must be a non-empty string")
        if vector_size <= 0:
            raise ValueError("vector_size must be > 0")

        if resolved_collection in self.list_collections():
            return

        url = f"{self._base_url}/collections/{resolved_collection}"
        headers: dict[str, str] = {}
        if self._api_key:
            headers["api-key"] = self._api_key

        payload = {"vectors": {"size": int(vector_size), "distance": distance}}
        with httpx.Client() as client:
            response = client.put(url, json=payload, headers=headers, timeout=30.0)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover
                detail = response.text.strip()
                raise httpx.HTTPStatusError(
                    f"{exc}. Body: {detail[:500]}",
                    request=exc.request,
                    response=exc.response,
                ) from exc

    def get_vector_params(self, *, collection: str) -> tuple[int, str | None]:
        """Return (vector_size, vector_name) for a collection.

        - vector_name is None when the collection uses a single unnamed vector.
        - vector_name is a string when the collection uses named vectors.
        """
        resolved_collection = collection.strip()
        if not resolved_collection:
            raise ValueError("collection must be a non-empty string")

        url = f"{self._base_url}/collections/{resolved_collection}"
        headers: dict[str, str] = {}
        if self._api_key:
            headers["api-key"] = self._api_key

        with httpx.Client() as client:
            response = client.get(url, headers=headers, timeout=15.0)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover
                detail = response.text.strip()
                raise httpx.HTTPStatusError(
                    f"{exc}. Body: {detail[:500]}",
                    request=exc.request,
                    response=exc.response,
                ) from exc
            data = response.json()

        result = data.get("result") if isinstance(data, dict) else None
        config = result.get("config") if isinstance(result, dict) else None
        params = config.get("params") if isinstance(config, dict) else None
        vectors = params.get("vectors") if isinstance(params, dict) else None

        # Qdrant formats:
        # - single vector: {"size": 4096, "distance": "Cosine"}
        # - named vectors: {"name": {"size": 4096, "distance": "Cosine"}, ...}
        if isinstance(vectors, dict) and "size" in vectors:
            raw_size = vectors.get("size")
            if not isinstance(raw_size, (int, float, str)):
                raise ValueError(f"Invalid vector size in Qdrant collection config: {raw_size!r}")
            size = int(raw_size)
            return size, None

        if isinstance(vectors, dict):
            candidates = [(name, spec) for name, spec in vectors.items() if isinstance(name, str)]
            for name, spec in candidates:
                if isinstance(spec, dict) and "size" in spec:
                    raw_size = spec.get("size")
                    if not isinstance(raw_size, (int, float, str)):
                        raise ValueError(
                            f"Invalid vector size in Qdrant collection config for {name!r}: {raw_size!r}"
                        )
                    size = int(raw_size)
                    return size, name

        raise ValueError(f"Unable to determine vector params for Qdrant collection {collection!r}.")

    def upsert(self, *, collection: str, points: list[dict]) -> None:
        resolved_collection = collection.strip()
        if not resolved_collection:
            raise ValueError("collection must be a non-empty string")
        if not isinstance(points, list) or not points:
            raise ValueError("points must be a non-empty list")

        url = f"{self._base_url}/collections/{resolved_collection}/points"
        headers: dict[str, str] = {}
        if self._api_key:
            headers["api-key"] = self._api_key

        payload = {"points": points}
        with httpx.Client() as client:
            response = client.put(url, params={"wait": "true"}, json=payload, headers=headers, timeout=30.0)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - depends on remote service
                detail = response.text.strip()
                raise httpx.HTTPStatusError(
                    f"{exc}. Body: {detail[:500]}",
                    request=exc.request,
                    response=exc.response,
                ) from exc
