from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable[[BaseModel], BaseModel | Any]
    input_model: type[BaseModel]
    description: str


def _is_pydantic_model(value: Any) -> bool:
    return isinstance(value, type) and issubclass(value, BaseModel)


def _find_module_input_model(tool_fn: Callable[..., Any]) -> type[BaseModel] | None:
    module = inspect.getmodule(tool_fn)
    if module is None:
        return None
    for name in ("InputSchema", "Input"):
        value = getattr(module, name, None)
        if _is_pydantic_model(value):
            return value
    return None


def _infer_input_model_and_executor(tool_fn: Callable[..., Any]) -> tuple[type[BaseModel], Callable[[BaseModel], Any]]:
    """Infer a Pydantic args model and return an executor that accepts that model.

    Supports two tool signatures:
      A) tool(InputModel) -> OutputModel
      B) tool(field1, field2, ...) -> primitive (module exposes Input/InputSchema matching params)
    """
    sig = inspect.signature(tool_fn)
    params = list(sig.parameters.values())

    # A) Single-arg Pydantic input model
    if len(params) == 1 and _is_pydantic_model(params[0].annotation):
        input_model = params[0].annotation

        def _exec_single(model: BaseModel) -> Any:
            return tool_fn(model)

        return input_model, _exec_single

    # B) Multi-arg primitive signature with module-level Input model
    input_model = _find_module_input_model(tool_fn)
    if input_model is None:
        raise TypeError(
            f"Tool {tool_fn} does not expose a supported Input model (expected InputSchema/Input)."
        )

    def _exec_kwargs(model: BaseModel) -> Any:
        payload = model.model_dump()
        return tool_fn(**payload)

    return input_model, _exec_kwargs


def _tool_wrapper(
    tool_fn: Callable[[BaseModel], Any],
    input_model: type[BaseModel],
    *,
    description: str,
) -> Callable[..., Any]:
    def _wrapped(**kwargs: Any) -> Any:
        validated = input_model.model_validate(kwargs)
        result = tool_fn(validated)
        if isinstance(result, BaseModel):
            return result.model_dump()
        return result

    _wrapped.__name__ = getattr(tool_fn, "__name__", "tool")
    _wrapped.__doc__ = description
    return _wrapped


def load_active_tool_specs() -> list[ToolSpec]:
    """Load curated tools from tools/__init__.py with their stable alias names."""
    import tools  # noqa: WPS433

    specs: list[ToolSpec] = []
    for name in getattr(tools, "__all__", []):
        if not isinstance(name, str):
            continue
        if name == "ACTIVE_TOOLS":
            continue
        value = getattr(tools, name, None)
        if not callable(value):
            continue
        input_model, executor = _infer_input_model_and_executor(value)
        desc = (inspect.getdoc(value) or "").strip() or f"Deterministic tool: {name}"
        specs.append(ToolSpec(name=name, fn=executor, input_model=input_model, description=desc))

    if not specs:
        raise RuntimeError("No active tools were discovered from tools.__all__.")
    return specs


def build_langchain_tools() -> list[StructuredTool]:
    """Build LangChain StructuredTool objects for ACTIVE_TOOLS injection (no tool RAG)."""
    tools: list[StructuredTool] = []
    for spec in load_active_tool_specs():
        wrapped = _tool_wrapper(spec.fn, spec.input_model, description=spec.description)
        tools.append(
            StructuredTool.from_function(
                func=wrapped,
                name=spec.name,
                description=spec.description,
                args_schema=spec.input_model,
                infer_schema=False,
            )
        )
    return tools


def resolve_tool_specs_by_name() -> dict[str, ToolSpec]:
    return {spec.name: spec for spec in load_active_tool_specs()}
