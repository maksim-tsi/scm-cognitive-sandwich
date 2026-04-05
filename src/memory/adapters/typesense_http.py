from __future__ import annotations

import httpx


class TypesenseHttpAdapter:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        resolved = base_url.strip().rstrip("/")
        if not resolved:
            raise ValueError("Typesense base_url must be a non-empty URL")
        resolved_key = api_key.strip()
        if not resolved_key:
            raise ValueError("Typesense api_key must be set")
        self._base_url = resolved
        self._api_key = resolved_key

    def list_collections(self) -> list[str]:
        url = f"{self._base_url}/collections"
        headers = {"X-TYPESENSE-API-KEY": self._api_key}
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

        names: list[str] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    names.append(item["name"])
        return names

    def ensure_collection(self, *, schema: dict) -> None:
        name = schema.get("name") if isinstance(schema, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Typesense collection schema must include non-empty 'name'")
        if name in self.list_collections():
            return

        url = f"{self._base_url}/collections"
        headers = {"X-TYPESENSE-API-KEY": self._api_key}
        with httpx.Client() as client:
            response = client.post(url, json=schema, headers=headers, timeout=30.0)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover
                detail = response.text.strip()
                raise httpx.HTTPStatusError(
                    f"{exc}. Body: {detail[:500]}",
                    request=exc.request,
                    response=exc.response,
                ) from exc

    def upsert(self, *, collection: str, document: dict) -> None:
        resolved_collection = collection.strip()
        if not resolved_collection:
            raise ValueError("collection must be a non-empty string")
        if not isinstance(document, dict):
            raise ValueError("document must be an object")

        url = f"{self._base_url}/collections/{resolved_collection}/documents"
        headers = {"X-TYPESENSE-API-KEY": self._api_key}
        with httpx.Client() as client:
            response = client.post(
                url,
                params={"action": "upsert"},
                json=document,
                headers=headers,
                timeout=30.0,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover
                detail = response.text.strip()
                raise httpx.HTTPStatusError(
                    f"{exc}. Body: {detail[:500]}",
                    request=exc.request,
                    response=exc.response,
                ) from exc
