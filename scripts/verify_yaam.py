import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import find_dotenv, load_dotenv

# Ensure src directory is importable when executing from workspace root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"{key} must be set for verify_yaam.py")
    return value.strip().strip("'").strip('"')


def main() -> int:
    from memory.adapters.qdrant_http import QdrantHttpAdapter  # noqa: WPS433
    from memory.adapters.typesense_http import TypesenseHttpAdapter  # noqa: WPS433
    from memory.models import KnowledgeDocument  # noqa: WPS433

    qdrant_url = _require_env("QDRANT_URL")
    qdrant_collection = _require_env("QDRANT_COLLECTION")
    typesense_url = _require_env("TYPESENSE_URL")
    typesense_key = _require_env("TYPESENSE_API_KEY")
    typesense_collection = _require_env("TYPESENSE_COLLECTION")

    # Required namespace env vars for Exec Plan 3 isolation (enforced here as well).
    _require_env("REDIS_PREFIX")
    _require_env("POSTGRES_DB")

    qdrant_api_key = (os.getenv("QDRANT_API_KEY") or "").strip()
    qdrant = QdrantHttpAdapter(base_url=qdrant_url, api_key=qdrant_api_key or None)

    available = qdrant.list_collections()
    if qdrant_collection not in available:
        qdrant.ensure_collection(collection=qdrant_collection, vector_size=4096, distance="Cosine")
        print(f"QDRANT CREATED collection={qdrant_collection}")

    vector_size, vector_name = qdrant.get_vector_params(collection=qdrant_collection)
    if vector_size != 4096:
        raise ValueError(
            "Qdrant collection vector size mismatch: "
            f"expected 4096 for qwen/qwen3-embedding-8b, got {vector_size}."
        )
    vector = [0.0] * vector_size

    vector_payload = vector if vector_name is None else {vector_name: vector}
    point = {
        "id": str(uuid4()),
        "vector": vector_payload,
        "payload": {"kind": "verify", "ts": datetime.now(tz=UTC).isoformat()},
    }

    qdrant.upsert(collection=qdrant_collection, points=[point])
    print(f"QDRANT OK collection={qdrant_collection} status_code=20X")

    typesense = TypesenseHttpAdapter(base_url=typesense_url, api_key=typesense_key)
    if typesense_collection not in typesense.list_collections():
        schema = {
            "name": typesense_collection,
            "fields": [
                {"name": "id", "type": "string"},
                {"name": "session_id", "type": "string", "optional": True},
                {"name": "title", "type": "string"},
                {"name": "content", "type": "string"},
                {"name": "knowledge_type", "type": "string", "optional": True},
                {"name": "confidence_score", "type": "float", "optional": True},
                {"name": "source_episode_ids", "type": "string[]", "optional": True},
                {"name": "episode_count", "type": "int32", "optional": True},
                {"name": "provenance_links", "type": "string[]", "optional": True},
                {"name": "category", "type": "string", "optional": True},
                {"name": "tags", "type": "string[]", "optional": True},
                {"name": "domain", "type": "string", "optional": True},
                {"name": "distilled_at", "type": "int64"},
                {"name": "access_count", "type": "int32", "optional": True},
                {"name": "usefulness_score", "type": "float", "optional": True},
                {"name": "validation_count", "type": "int32", "optional": True},
            ],
            "default_sorting_field": "distilled_at",
        }
        typesense.ensure_collection(schema=schema)
        print(f"TYPESENSE CREATED collection={typesense_collection}")

    doc = KnowledgeDocument(
        knowledge_id="verify-doc",
        session_id="verify-session",
        title="Verify YAAM Typesense Upsert",
        content="This is a dummy document for Typesense connectivity verification.",
        knowledge_type="insight",
        confidence_score=0.5,
        source_episode_ids=[],
        episode_count=0,
        provenance_links=[],
        category="winsim",
        tags=["verify"],
        domain="scm",
        metadata={"kind": "verify"},
    ).to_typesense_document()

    typesense.upsert(collection=typesense_collection, document=doc)
    print(f"TYPESENSE OK collection={typesense_collection} status_code=20X")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
