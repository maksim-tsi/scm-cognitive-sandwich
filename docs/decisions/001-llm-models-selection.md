# ADR 001: LLM Models Selection for Phase 2

## Status
Accepted

## Context
As part of Phase 2 (LLM and API Integration), we've migrated to LangChain to support multiple LLM providers: Groq, Google, and Mistral. It is critical to pin the models to specific, current versions to ensure we do not use outdated, unoptimized, or deprecated models.

## Decision
We have decided to use the following exact models for our LangGraph orchestration nodes:
- **Mistral**: `mistral-medium-2508`
- **Google Generative AI (Gemini)**: `gemini-3.1-flash-lite-preview`
- **Groq**: `openai/gpt-oss-120b`

These models must be properly instantiated in our scripts (e.g. `check_llm_health.py`) and agent code (`src/agents/graph.py`).

## Consequences
- Guaranteed reproducibility of agent behavior using pinned model versions.
- If a model is deprecated, this ADR and the associated code must be updated.
- All environment setups must provide the respective API keys (`MISTRAL_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`) to properly interface with these models.
