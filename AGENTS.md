# Agent Directives: SCM Cognitive Sandwich 🥪

Welcome. You are an autonomous AI coding agent operating in an "Agent-First" repository. Your primary directive is to write code, tests, and maintain documentation without manual human coding. Humans steer, you execute.

This file is your **Map**, not your encyclopedia. For deep context, always refer to the `/docs` directory.

## 1. Core Beliefs & Operating Principles
* **The Sandwich Pattern:** The LLM never solves mathematical routing problems directly! The LLM translates text into JSON parameters (Artifact) -> A deterministic OR solver (SCIP) validates them -> The LLM analyzes error logs (IIS) and corrects the JSON.
* **YAAM is the Law:** To manage decision states, use *only* the `yaam` library tools (`artifact_save_draft`, `artifact_attach_feedback`, `artifact_create_revision`, `artifact_commit_final`). Do not invent local databases or state files.
* **YAAM is a Read-Only Dependency:** The yaam package is an external library installed in the virtual environment. You are strictly forbidden from attempting to navigate to or modify any YAAM source code. You must interact with YAAM solely by importing its public interfaces (e.g., yaam.agents.tools) inside src/memory/yaam_facade.py.
* **External Ground Truth:** To check port statuses, the agent must always make an HTTP request to the external API (`maritime-port-sandbox`), rather than relying on its internal parametric knowledge.
* **Mechanical Enforcement:** Rely on `ruff`, `mypy`, and `pytest`. If a linter or test fails, read the traceback and fix the code yourself. Ignoring strict typing is forbidden.

## 2. Knowledge Map (Where to find things)
Before starting any task, study the documentation in the `/docs` directory:

* **`/docs/architecture/index.md`** - System design, LangGraph structure, and boundaries between the agent and the OR solver (Pyomo).
* **`/docs/domain/sandwich-loop.md`** - Business logic: how the DCSA JSON is formed, how the SCIP solver works, and what an Irreducible Infeasible Subsystem (IIS) is.
* **`/docs/exec-plans/active/`** - Step-by-step execution plans for current tasks. Always update your progress here.
* **`/docs/decisions/`** - Architectural Decision Records (ADRs).

## 3. Workflow Instructions
When assigned a task, strictly follow this loop:
1. **Discover:** Read the task, study the codebase and relevant files in `/docs`.
2. **Plan:** If the task is complex, write a markdown plan in `/docs/exec-plans/active/` before writing code.
3. **Execute:** Write the code. You MUST create and update `pytest` tests for any new LangGraph node or mathematical constraint in Pyomo.
4. **Validate:** Run `pytest` and `ruff check .`. Fix all discovered errors yourself.
5. **Document:** If you change the agent structure, solver logic, or prompts, update the relevant files in `/docs/`.

## 4. Tech Stack Constraints
* **Language:** Python 3.11+
* **Orchestration:** LangGraph (agent state machine) & LangChain
* **Mathematical Core:** Pyomo (model generation) + SCIP Solver
* **Memory Management:** Integration with `yaam` (Yet Another Agents Memory)
* **Typing & Validation:** Pydantic v2 (Strict mode)

*End of Directives. Look at the task and begin your discovery phase.*