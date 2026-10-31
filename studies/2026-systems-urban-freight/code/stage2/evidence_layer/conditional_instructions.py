"""Finite, public-fact conditional clause selection for Stage 2 instructions.

This selects text only. It does not extract a value, infer the truth of a
condition, or determine whether the selected instruction is authoritative.
Unknown facts and unsupported/multiple conditions fail closed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

# Explicit public vocabulary. Values are packet facts supplied before the
# runtime decision; no fact is inferred from instruction prose.
CONDITION_ALIASES: dict[str, tuple[str, ...]] = {
    "booking_confirmed": (r"booking\s+is\s+confirmed", r"confirmed\s+booking"),
    "receiver_present": (r"receiver\s+is\s+present", r"receiver\s+present"),
    "forklift_available": (r"forklift\s+is\s+available", r"forklift\s+available"),
    "stocktake_morning": (
        r"stocktake\s+(?:is\s+)?(?:not\s+)?(?:in\s+the\s+)?morning",
        r"morning\s+stocktake",
        r"stocktake\s+during\s+the\s+morning",
    ),
    "first_vehicle": (
        r"first\s+vehicle",
        r"first\s+truck",
        r"first\s+delivery\s+vehicle",
    ),
    "sealed_pallets": (
        r"pallets?\s+(?:are\s+)?(?:not\s+)?sealed",
        r"sealed\s+pallets?",
    ),
    "first_monday": (
        r"(?:(?:(?:this|the)\s+)?month['’]s\s+)?first\s+monday(?:\s+of\s+(?:(?:the|a|this)\s+)?month)?",
    ),
    "fewer_than_four_cages": (
        r"fewer\s+than\s+(?:four|4)\s+cages?",
        r"less\s+than\s+(?:four|4)\s+cages?",
        r"under\s+(?:four|4)\s+cages?",
    ),
    "loading_bay_staffed": (
        r"loading\s+bay\s+(?:is\s+)?staffed",
        r"dock\s+(?:is\s+)?staffed",
        r"staffed\s+loading\s+bay",
    ),
    "loading_team_available": (
        r"loading\s+team\s+(?:is\s+)?(?:available|present)",
        r"loading\s+crew\s+(?:is\s+)?(?:available|present)",
    ),
    "loading_available": (
        r"loading\s+(?:is\s+)?available",
        r"loading\s+facilities\s+(?:are\s+)?available",
    ),
}

_INTRODUCER = re.compile(
    r"\b(only\s+when|only\s+if|provided(?:\s+that)?|unless|if|when|for(?=[^,;:.]{0,80}first\s+monday\b[^,;:.]{0,30}\bonly\b)|on(?=\s+(?:the\s+)?(?:first\s+monday|stocktake\s+morning)))\b",
    re.IGNORECASE,
)
_BRANCH_DELIMITER = re.compile(r"\s*(?:,|;|:|\bthen\b)\s*", re.IGNORECASE)
_ALTERNATIVE = re.compile(
    r"\b(?:otherwise|else|(?:on\s+)?(?:all|every)\s+other\s+(?:dates?|days?|mornings?))\b",
    re.IGNORECASE,
)


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def _result(
    status: str,
    *,
    selected_text: str | None = None,
    condition: str | None = None,
    fact_key: str | None = None,
    required_value: bool | None = None,
    fact_value: bool | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "selected_text": selected_text,
        "condition": condition,
        "fact_key": fact_key,
        "required_value": required_value,
        "fact_value": fact_value,
        "reason": reason,
    }


def _match_condition(text: str) -> tuple[str | None, str | None, bool | None]:
    """Return (canonical phrase, fact key, positive polarity) if unique."""
    hits: list[tuple[str, str, re.Match[str]]] = []
    for fact_key, aliases in CONDITION_ALIASES.items():
        for alias in aliases:
            for match in re.finditer(
                r"(?<!\w)(?:" + alias + r")(?!\w)", text, re.IGNORECASE
            ):
                hits.append((fact_key, alias, match))
    # Several aliases may describe the same words. Deduplicate overlapping
    # matches for a single fact, but fail when distinct facts are named.
    by_fact: dict[str, list[tuple[str, re.Match[str]]]] = {}
    for fact_key, alias, match in hits:
        by_fact.setdefault(fact_key, []).append((alias, match))
    if len(by_fact) > 1:
        return None, "__multiple__", None
    if len(by_fact) != 1:
        return None, None, None
    fact_key, found = next(iter(by_fact.items()))
    match = max(found, key=lambda item: item[1].end() - item[1].start())[1]
    before = text[max(0, match.start() - 16) : match.start()]
    after = text[match.end() : match.end() + 16]
    negated = (
        bool(re.search(r"\bnot(?:\s+the)?\s*$|\bnever\s*$", before))
        or bool(re.match(r"\s+(?:is\s+)?not\b", after))
        or bool(re.search(r"\bnot\b", match.group(0)))
    )
    return match.group(0), fact_key, not negated


def _select_branch(content: str, facts: Mapping[str, Any] | None) -> dict[str, Any]:
    """Select a single conditional clause using trusted boolean packet facts.

    The result status is one of `no_condition`, `selected`,
    `no_applicable_clause`, `unknown_condition`, `unsupported_condition`,
    `multiple_conditions`, `malformed`, or `invalid_input`. A selected result
    returns the operative clause text and removes the condition marker and
    unused alternative. No value is predicted.
    """
    if not isinstance(content, str) or not content.strip():
        return _result("invalid_input", reason="content_must_be_nonempty_text")
    text = unicodedata.normalize("NFKC", content).strip()
    introducers = list(_INTRODUCER.finditer(text))
    if not introducers:
        return _result("no_condition", selected_text=text)
    if len(introducers) > 1:
        return _result(
            "multiple_conditions", reason="more_than_one_condition_introducer"
        )

    marker = introducers[0]
    delimiter = _BRANCH_DELIMITER.search(text, marker.end())
    if delimiter is None:
        return _result("malformed", reason="condition_has_no_clause_delimiter")
    condition_text = text[marker.end() : delimiter.start()].strip()
    condition, fact_key, condition_polarity = _match_condition(_normal(condition_text))
    if fact_key == "__multiple__":
        return _result(
            "multiple_conditions",
            condition=condition_text,
            reason="condition_names_multiple_facts",
        )
    if fact_key is None:
        return _result(
            "unsupported_condition",
            condition=condition_text,
            reason="condition_not_in_public_vocabulary_or_compound",
        )
    # Reject instructions accidentally swallowed into the condition when a
    # comma/then separator is missing (e.g. "If first Monday use 08:00").
    residual = re.sub(re.escape(condition or ""), " ", _normal(condition_text), count=1)
    residual = re.sub(
        r"\b(?:it|is|the|a|an|on|in|at|during|of|this|that|month|not|never|only)\b",
        " ",
        residual,
    )
    if residual.strip():
        return _result(
            "malformed",
            condition=condition,
            fact_key=fact_key,
            reason="condition_clause_not_separated",
        )

    introducer = marker.group(1).casefold()
    # A condition is active for IF/ONLY IF/ONLY WHEN/PROVIDED when true and
    # for UNLESS when false. A negative condition phrase flips that polarity.
    required_value = condition_polarity
    if introducer == "unless":
        required_value = not required_value

    body_start = delimiter.end()
    body = text[body_start:].strip()
    alternatives = list(_ALTERNATIVE.finditer(body))
    if len(alternatives) > 1:
        return _result(
            "multiple_conditions",
            condition=condition,
            fact_key=fact_key,
            reason="multiple_alternative_clauses",
        )
    if alternatives:
        split = alternatives[0]
        true_text = body[: split.start()].strip(" ,;:.")
        false_text = body[split.end() :].strip(" ,;:.")
        if not true_text or not false_text:
            return _result(
                "malformed",
                condition=condition,
                fact_key=fact_key,
                reason="empty_conditional_branch",
            )
    else:
        true_text, false_text = body.strip(" ,;:."), ""
        if not true_text:
            return _result(
                "malformed",
                condition=condition,
                fact_key=fact_key,
                reason="empty_conditional_branch",
            )

    if not isinstance(facts, Mapping) or fact_key not in facts:
        return _result(
            "unknown_condition",
            condition=condition,
            fact_key=fact_key,
            required_value=required_value,
            reason="trusted_fact_not_provided",
        )
    fact_value = facts[fact_key]
    if not isinstance(fact_value, bool):
        return _result(
            "unknown_condition",
            condition=condition,
            fact_key=fact_key,
            required_value=required_value,
            fact_value=None,
            reason="trusted_fact_is_not_boolean",
        )

    is_conditional_branch = fact_value == required_value
    selected = true_text if is_conditional_branch else false_text
    if not selected:
        return _result(
            "no_applicable_clause",
            condition=condition,
            fact_key=fact_key,
            required_value=required_value,
            fact_value=fact_value,
            reason="condition_false_and_no_alternative_clause",
        )
    return _result(
        "selected",
        selected_text=selected,
        condition=condition,
        fact_key=fact_key,
        required_value=required_value,
        fact_value=fact_value,
    )


def select_branch(content: str, facts: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return clause selection and the position of its own condition marker.

    Consumers must not search for a second, differently defined introducer.
    """
    text = (
        unicodedata.normalize("NFKC", content) if isinstance(content, str) else content
    )
    result = _select_branch(text, facts)
    marker = _INTRODUCER.search(text) if isinstance(text, str) else None
    result["condition_start"] = marker.start() if marker else None
    return result
