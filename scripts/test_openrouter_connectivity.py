import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, Field

# Ensure src directory is in path (match other scripts)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))


# Load .env early so OpenRouter env vars exist before model init.
_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)


class DummyScenario(BaseModel):
    model_config = ConfigDict(strict=True)

    scenario_id: str = Field(..., description="Short stable id like S1/S2/S3.")
    title: str = Field(..., description="Short scenario name.")
    summary: str = Field(..., description="One sentence summary.")


class DummyScenarioList(BaseModel):
    model_config = ConfigDict(strict=True)

    scenarios: list[DummyScenario] = Field(..., min_length=3, max_length=3)


def main() -> int:
    from llm.call_llm import get_openrouter_chat  # noqa: WPS433
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: WPS433

    model = os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL")
    if not model:
        raise SystemExit("Missing LLM_MODEL (or OPENROUTER_MODEL) in environment.")

    if not os.getenv("OPENROUTER_API_KEY"):
        raise SystemExit("Missing OPENROUTER_API_KEY in environment.")

    # langchain-openrouter expects timeout in ms; our helper takes seconds and converts.
    llm = get_openrouter_chat(model=model, timeout_s=180.0).with_structured_output(DummyScenarioList)

    system = SystemMessage(content="You output STRICT JSON only. No prose.")
    human = HumanMessage(
        content=(
            "Generate exactly 3 dummy maritime logistics scenarios.\n"
            "Each scenario must have scenario_id (S1/S2/S3), title, summary.\n"
            "Return ONLY JSON that matches DummyScenarioList."
        )
    )

    print(f"Using model={model!r} timeout_s=180.0")
    result = llm.invoke([system, human])
    parsed = result if isinstance(result, DummyScenarioList) else DummyScenarioList.model_validate(result)

    print("OK: structured output parsed")
    print(f"type={type(parsed)}")
    print(parsed.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
