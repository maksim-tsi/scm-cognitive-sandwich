"""Prospective synthetic evidence world: trusted server code, never a model sandbox.

No historical runtime imports. Semantic question fields are explicit controlled input;
free wording is preserved but not interpreted by a hidden LLM or approximate matcher.
"""
from __future__ import annotations

import copy
import hashlib
import heapq
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2].parent / "data"
TOOLS = ("lookup_snapshot", "sum_minutes", "intersect_bounds", "shortest_path", "check_feasibility")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_demo(name: str = "demo-allowance") -> dict[str, Any]:
    return dict(json.loads((ROOT / "research/p4/world/demos" / f"{name}.json").read_text()))


def eligible(fact: dict[str, Any], epoch: int, effective: int) -> bool:
    return bool(fact["verified"] and fact["available_at"] <= epoch
                and fact["effective_from"] <= effective < fact["effective_to"]
                and fact["authority"] == "confirmed" and fact["access"] != "UNKNOWN")


class World:
    """Episode-local trusted world. Only serialized methods below are agent-visible."""

    def __init__(self, definition: dict[str, Any], *, tools: bool = True, user_answers: bool = True):
        self._definition = copy.deepcopy(definition)
        self.tools_enabled = tools
        self.answers_enabled = user_answers
        self.reset()

    def reset(self) -> None:
        self.questions = 0
        self.tool_calls = 0
        self.turns = 0
        self.acquired: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._terminal = False
        self._bounds: tuple[float, float] | None = None

    def observe_public_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._definition["public"])

    def _record(self, action: str, arguments: Any, response: Any) -> None:
        previous = self._events[-1]["hash"] if self._events else "0" * 64
        event = {"episode": self._definition["id"], "sequence": len(self._events) + 1,
                 "action": action, "arguments": copy.deepcopy(arguments), "response": copy.deepcopy(response),
                 "questions_used": self.questions, "tools_used": self.tool_calls,
                 "logical_turn": self.turns, "condition": {"tools": self.tools_enabled, "user_answers": self.answers_enabled},
                 "previous_hash": previous}
        event["hash"] = digest(event)
        self._events.append(event)

    def _turn(self) -> str | None:
        if self._terminal:
            return "TERMINAL"
        if self.turns >= 7:
            return "TURN_LIMIT_EXCEEDED"
        self.turns += 1
        return None

    def _match(self, entity: str, field: str, scope: str) -> list[dict[str, Any]]:
        return [f for f in self._definition["facts"]
                if f["entity"] == entity and f["field"] == field and f["scope"] == scope]

    def _release(self, fact: dict[str, Any], channel: str) -> dict[str, Any]:
        if fact["available_at"] > self._definition["epoch"]:
            return {"status": "TEMPORALLY_UNAVAILABLE"}
        if fact["access"] == "RESTRICTED_OR_FUTURE":
            return {"status": "NOT_AUTHORIZED"}
        if fact["access"] == "UNKNOWN":
            return {"status": "UNKNOWN"}
        if not eligible(fact, self._definition["epoch"], self._definition["effective_time"]):
            return {"status": "NOT_AUTHORIZED"}
        if channel == "user" and fact["access"] == "TOOL_REQUIRED":
            return {"status": "TOOL_REQUIRED"}
        if channel == "tool" and fact["access"] == "USER_KNOWN":
            return {"status": "NOT_TOOL_KNOWN"}
        if channel == "user" and fact["owner"] != "dispatcher":
            return {"status": "NOT_AUTHORIZED"}
        self.acquired[fact["id"]] = copy.deepcopy(fact)
        return {"status": "ANSWERED" if channel == "user" else "OK", "fact_id": fact["id"],
                "value": fact["value"], "unit": fact["unit"], "provenance": fact["source"],
                "entity": fact["entity"], "field": fact["field"], "scope": fact["scope"]}

    def ask_user(self, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(questions, list) or not all(isinstance(q, dict) for q in questions):
            self._turn()
            response = [{"status": "INVALID_ARGUMENTS"}]
            self._record("ASK_USER_INVALID", {"invalid_outer_type": True}, response)
            return response
        blocked = self._turn()
        responses: list[dict[str, Any]] = []
        if blocked:
            responses = [{"status": blocked} for _ in questions]
        elif len(questions) > 3 - self.questions:
            self.questions = 3  # Overflow rejects the whole bundle; remaining slots are consumed.
            responses = [{"status": "QUESTION_LIMIT_EXCEEDED"} for _ in questions]
        else:
            for question in questions:
                if self.questions >= 3:
                    responses.append({"status": "QUESTION_LIMIT_EXCEEDED"})
                    continue
                self.questions += 1  # Invalid, redundant and unanswerable atomic requests count.
                if not self.answers_enabled:
                    responses.append({"status": "ANSWERS_DISABLED"})
                    continue
                required = ("wording", "entity", "field", "scope", "owner", "kind")
                if set(question) != set(required) or any(not isinstance(question.get(k), str) or not question[k] for k in required):
                    responses.append({"status": "AMBIGUOUS_QUESTION"})
                    continue
                if question["kind"] not in ("indispensable", "optional") or question["owner"] != "dispatcher":
                    responses.append({"status": "NOT_AUTHORIZED"})
                    continue
                matches = self._match(question["entity"], question["field"], question["scope"])
                if len(matches) != 1:
                    responses.append({"status": "AMBIGUOUS_QUESTION" if matches else "UNKNOWN"})
                else:
                    responses.append(self._release(matches[0], "user"))
        self._record("ASK_USER", questions, responses)
        return responses

    def call_tool(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(tool_id, str) or not isinstance(arguments, dict):
            self._turn()
            response = {"status": "INVALID_ARGUMENTS"}
            self._record("CALL_TOOL_INVALID", {"invalid_outer_type": True}, response)
            return response
        blocked = self._turn()
        if blocked:
            result = {"status": blocked}
        elif self.tool_calls >= 3:
            result = {"status": "TOOL_LIMIT_EXCEEDED"}
        else:
            self.tool_calls += 1
            if not self.tools_enabled:
                result = {"status": "NOT_AUTHORIZED"}
            elif tool_id not in TOOLS:
                result = {"status": "UNKNOWN_TOOL"}
            else:
                try:
                    result = self._execute(tool_id, arguments)
                except (ValueError, TypeError, KeyError, IndexError):
                    result = {"status": "INVALID_ARGUMENTS"}
        self._record("CALL_TOOL", {"tool": tool_id, "arguments": arguments}, result)
        return result

    @staticmethod
    def _numbers(values: Any) -> list[float]:
        if not isinstance(values, list) or not values or any(type(v) not in (int, float) for v in values):
            raise ValueError("numeric list required")
        canonical(values)  # Reject NaN/Infinity.
        return list(values)

    def _execute(self, tool_id: str, args: dict[str, Any]) -> dict[str, Any]:
        expected = {"lookup_snapshot": {"entity", "field", "scope"}, "sum_minutes": {"values"},
                    "intersect_bounds": {"lower", "upper"}, "shortest_path": {"edges", "start", "end"},
                    "check_feasibility": {"duration"}}
        if set(args) != expected[tool_id]:
            raise ValueError("unexpected argument")
        if tool_id == "lookup_snapshot":
            if not all(isinstance(v, str) for v in args.values()):
                raise ValueError("string arguments required")
            facts = self._match(args["entity"], args["field"], args["scope"])
            return self._release(facts[0], "tool") if len(facts) == 1 else {"status": "NOT_FOUND"}
        if tool_id == "sum_minutes":
            return {"status": "OK", "value": sum(self._numbers(args["values"])), "unit": "minutes"}
        if tool_id == "intersect_bounds":
            lower, upper = max(self._numbers(args["lower"])), min(self._numbers(args["upper"]))
            self._bounds = (lower, upper)
            return {"status": "OK", "lower": lower, "upper": upper, "feasible": lower <= upper}
        if tool_id == "check_feasibility":
            duration = self._numbers([args["duration"]])[0]
            if self._bounds is None:
                return {"status": "PRECONDITION_REQUIRED"}
            low, high = self._bounds
            return {"status": "OK", "feasible": duration >= 0 and low + duration <= high}
        if not isinstance(args["edges"], list) or not isinstance(args["start"], str) or not isinstance(args["end"], str):
            raise TypeError("invalid graph")
        graph: dict[str, list[tuple[str, float]]] = {}
        for edge in args["edges"]:
            if not isinstance(edge, list) or len(edge) != 3 or not isinstance(edge[0], str) or not isinstance(edge[1], str):
                raise ValueError("invalid edge")
            weight = self._numbers([edge[2]])[0]
            if weight < 0:
                raise ValueError("nonnegative graph required")
            graph.setdefault(edge[0], []).append((edge[1], weight))
        heap: list[tuple[float, str]] = [(0, args["start"])]
        visited: set[str] = set()
        while heap:
            cost, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)
            if node == args["end"]:
                return {"status": "OK", "distance": cost}
            for target, weight in sorted(graph.get(node, [])):
                if target not in visited:
                    heapq.heappush(heap, (cost + weight, target))
        return {"status": "NO_PATH"}

    def submit_final(self, decision: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(decision, dict):
            self._turn()
            self._terminal = True
            response = {"status": "MALFORMED"}
            self._record("FINAL_INVALID", {"invalid_outer_type": True}, response)
            return response
        try:
            canonical(decision)
        except (ValueError, TypeError):
            self._turn()
            self._terminal = True
            response = {"status": "MALFORMED"}
            self._record("FINAL_INVALID", {"non_json_value": True}, response)
            return response
        blocked = self._turn()
        if blocked:
            result = {"status": blocked}
        else:
            # Mandatory structural validation is independent of voluntary tool use.
            valid = (set(decision) in ({"action", "value", "evidence"}, {"action", "value", "evidence", "missing_slots"})
                     and isinstance(decision.get("action"), str)
                     and decision["action"] in {"UPDATE", "RETAIN", "CLARIFY", "INSUFFICIENT"}
                     and isinstance(decision["evidence"], list)
                     and all(isinstance(x, str) for x in decision["evidence"])
                     and (type(decision["value"]) in (int, float) and math.isfinite(decision["value"])
                          or decision["value"] is None)
                     and isinstance(decision.get("missing_slots", []), list)
                     and all(isinstance(x, str) for x in decision.get("missing_slots", [])))
            result = {"status": "SUBMITTED" if valid else "MALFORMED"}
            self._terminal = True
        self._record("FINAL", decision, result)
        return result

    def export_trace(self) -> bytes:
        return ("".join(canonical(event) + "\n" for event in self._events)).encode()


def evaluate(definition: dict[str, Any], trace: bytes, *, expected_condition: dict[str, bool] | None = None) -> dict[str, Any]:
    """Independent source-first evaluator, not an agent-callable tool.

    Reference value derives from immutable synthetic facts, not the agent's answer.
    This tiny demo evaluator deliberately supports one scalar task only.
    """
    try:
        events = [json.loads(line) for line in trace.splitlines()]
        if any(not isinstance(event, dict) for event in events):
            raise ValueError("event object required")
        condition = expected_condition if expected_condition is not None else {"tools": True, "user_answers": True}
        if any(event.get("condition") != condition for event in events):
            raise ValueError("assigned condition mismatch")
        replay = World(definition, **condition)
        for event in events:
            if event["action"] == "ASK_USER":
                replay.ask_user(event["arguments"])
            elif event["action"] == "CALL_TOOL":
                replay.call_tool(event["arguments"]["tool"], event["arguments"]["arguments"])
            elif event["action"] == "FINAL":
                replay.submit_final(event["arguments"])
            else:
                raise ValueError("unknown event")
        if replay.export_trace() != trace:
            raise ValueError("trace mismatch")
    except (ValueError, TypeError, KeyError):
        return {"attempted": 1, "status": "INVALID_TRACE", "correct": False}
    finals = [event for event in events if event["action"] == "FINAL" and event["response"]["status"] == "SUBMITTED"]
    if len(finals) != 1:
        return {"attempted": 1, "status": "INCOMPLETE", "correct": False}
    observed: set[str] = set()
    for event in events[:events.index(finals[0])]:
        responses = event["response"] if isinstance(event["response"], list) else [event["response"]]
        for response in responses:
            if response.get("status") in ("ANSWERED", "OK") and "fact_id" in response:
                observed.add(response["fact_id"])
    matching = [f for f in definition["facts"] if f["entity"] == definition["public"]["entity"]
                and f["field"] == definition["public"]["field"] and f["scope"] == definition["public"]["scope"]]
    relevant = [f for f in matching if eligible(f, definition["epoch"], definition["effective_time"])]
    uncertain = any(f["authority"] == "unknown" and f["available_at"] <= definition["epoch"]
                    and f["effective_from"] <= definition["effective_time"] < f["effective_to"] for f in matching)
    if uncertain or len(relevant) > 1:
        return {"attempted": 1, "status": "UNRESOLVED_REFERENCE", "correct": False}
    decision = finals[0]["arguments"]
    cited = set(decision["evidence"])
    usable = [fact for fact in relevant if fact["id"] in observed and fact["id"] in cited]
    expected = relevant[0]["value"] if len(relevant) == 1 else None
    correct = bool(len(usable) == 1 and expected is not None and decision["value"] == expected
                   and decision["action"] == ("RETAIN" if expected == definition["public"]["current"] else "UPDATE"))
    expected_action = "RETAIN" if expected == definition["public"]["current"] else "UPDATE"
    if not any(fact["id"] in observed for fact in relevant):
        user_reachable = any(f["owner"] == "dispatcher" and f["access"] in ("USER_KNOWN", "BOTH_AVAILABLE") for f in relevant) and condition["user_answers"]
        tool_reachable = any(f["access"] in ("TOOL_REQUIRED", "BOTH_AVAILABLE") for f in relevant) and condition["tools"]
        questions_used = max((e["questions_used"] for e in events), default=0)
        expected_action = ("CLARIFY" if questions_used < 3 else "QUESTION_BUDGET_EXHAUSTED") if user_reachable else "PENDING_TOOL" if tool_reachable else "INSUFFICIENT"
        correct = bool(decision["action"] == expected_action and decision["value"] is None
                       and decision.get("missing_slots") == [definition["public"]["field"]]
                       and not cited)
    return {"attempted": 1, "status": "EVALUATED", "correct": correct,
            "reference_action_at_observed_state": expected_action,
            "unsupported_numeric": decision["action"] in ("UPDATE", "RETAIN") and not usable,
            "questions": sum(len(e["arguments"]) for e in events if e["action"] == "ASK_USER")}
