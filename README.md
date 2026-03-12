# SCM Sandwich Agent: LLM-Solver-LLM Orchestrator 🥪

This repository contains the core orchestration logic for the **Artifact-Centric "Sandwich" Cognitive Architecture**, designed for autonomous supply chain disruption management. It bridges the semantic reasoning capabilities of Large Language Models (LLMs) with the mathematical rigor of Operations Research (OR) solvers.

This codebase is the experimental foundation for our IDWL 2026 paper: *"Artifact-Centric Cognitive Architecture for Freight Forwarders: Enhancing Climate Resilience through LLM-Solver Integration."*

## 🧠 The "Sandwich" Concept
Pure LLM agents hallucinate under strict mathematical constraints, while pure OR solvers fail when handling unstructured real-world chaos. This orchestrator solves this by explicitly separating concerns:

1. **Upstream LLM (Synthesizer):** Translates unstructured disruption alerts into a structured routing JSON (Artifact v1).
2. **Core Solver (Pyomo + SCIP):** Attempts to solve the capacity/routing matrix. If it fails (e.g., alternative port capacity exceeded), it generates an **Irreducible Infeasible Subsystem (IIS)** log.
3. **Downstream LLM (Interpreter/Repair):** Reads the mathematical IIS log, corrects the routing parameters, and iterates until the artifact is physically feasible (Artifact v2).

## 🗄️ Integration with YAAM
This agent relies heavily on **[YAAM (Yet Another Agents Memory)](https://github.com/maksim-tsi/yet-another-agents-memory)** for strict cognitive auditability. Using YAAM's artifact subsystem, the agent ensures that:
* Failed routing attempts and IIS logs are kept in transient Working Memory (L1/L2).
* The causal lineage (DAG) between v1, the solver's error, and v2 is explicitly mapped.
* Only the final, mathematically verified decision is committed to Semantic Memory (L4).

## ⚙️ Installation & Setup

### Prerequisites
* Python 3.11+
* **YAAM infrastructure running** (Redis, Postgres, Typesense, Neo4j).
* **SCIP Optimization Suite:** Open-source OR solver required for IIS extraction.

```bash
  # Linux/macOS
  pip install pyscipopt

```

### Running the Baseline Experiment

```bash
# Clone the repository
git clone https://github.com/maksim-tsi/scm-cognitive-sandwich.git
cd scm-cognitive-sandwich

# Install dependencies using Poetry
poetry install

# Run the IDWL 2026 Baseline Scenario
poetry run python scripts/run_idwl_baseline.py

```

## 📊 Expected Output (Baseline Scenario)

Running the baseline script will demonstrate the following loop:

1. Agent initializes with an alert: `"Hamburg port closed due to storm."`
2. Agent routes 100% of cargo to Rotterdam (Artifact v1).
3. SCIP Solver rejects v1 -> `IIS: Capacity of NLRTM exceeded by 500 TEU`.
4. Agent reads feedback, splits cargo between Rotterdam and Antwerp (Artifact v2).
5. SCIP Solver validates v2 -> `FEASIBLE`.
6. Artifact v2 and its lineage are committed to YAAM L4.

## 🤝 Architecture

* `src/agents/` - LangGraph definitions and prompt templates.
* `src/solver/` - Pyomo formulations and SCIP IIS extraction logic.
* `src/orchestrator/` - The loop tying the LLM, Solver, and YAAM memory tools together.

## 📝 License

MIT License.

