import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Ensure src directory is importable when executing from workspace root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)


def main() -> int:
    from llm.openrouter_embeddings import EXPECTED_DIMENSIONS, embed_text  # noqa: WPS433

    vector, latency_ms = embed_text(
        "verification text: scm-cognitive-sandwich winsim embedding healthcheck",
        model="qwen/qwen3-embedding-8b",
    )
    assert len(vector) == EXPECTED_DIMENSIONS
    print(
        "EMBED OK "
        f"model=qwen/qwen3-embedding-8b dims={len(vector)} embedding_latency_ms={latency_ms:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

