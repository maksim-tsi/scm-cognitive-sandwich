"""Common, packet-origin-based simulated-dispatcher authority closure.

This module classifies whether every indispensable fact requested by a public
output can be asked from the adopted dispatcher channel. It does not interpret
case labels, answer a question, disclose unreleased source content, or trust an
actor's assertion that a fact is reachable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

DISPATCHER = "dispatcher_instruction"
DISPATCHER_ONLY_SLOTS = {
    "effective_interval",
    "confirmation",
    "supporting_evidence",
    "interpretation",
    "interpretation_or_confirmation",
}
KNOWN_NON_DISPATCHER = {"receiver_confirmation", "signed_schedule"}


def _available_state(record: Mapping[str, Any], decision_time: str) -> str:
    """Describe release state without collapsing null/unknown into future."""
    value = record.get("available_at")
    if value is None:
        return "unknown"
    try:
        from .runtime import instant

        return "released" if instant(value) <= instant(decision_time) else "future"
    except (TypeError, ValueError):
        return "unknown"


def _origin(record: Mapping[str, Any]) -> str:
    source_type = record.get("source_type")
    verified = record.get("verified")
    if source_type == DISPATCHER and verified is True:
        return "dispatcher_owned"
    if source_type == DISPATCHER and verified is not True:
        return "unverified_dispatcher_origin"
    if source_type in KNOWN_NON_DISPATCHER:
        return "non_dispatcher_origin"
    # The public profile explicitly excludes authenticating unknown senders.
    return "unauthenticated_origin"


def _relevant_records(packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    field = packet.get("field")
    target = packet.get("target_entity")
    from .reason_predicates import plausible_entities
    from .runtime import (
        eligible_records,
        extract_value,
        relative_scope,
        released_packet,
    )

    candidates = plausible_entities(packet)
    if not target and len(candidates) > 1:
        # Scope admission, supersession and decisiveness inside each world.
        union = {}
        for entity in candidates:
            for record in _relevant_records(dict(packet, target_entity=entity)):
                union[record.get("id")] = record
        return list(union.values())
    potential_entities = set(candidates)
    public = released_packet(dict(packet))
    operative: list[dict[str, Any]] = []
    for entity in potential_entities:
        eligible, _ = eligible_records(public, entity)
        operative.extend(r for r in eligible if relative_scope(r, dict(packet)) is True)
    superseded = {old for r in operative for old in r.get("supersedes", [])}
    # A defective side report cannot make an otherwise supported decision
    # depend on re-authenticating that unrelated report.
    decisive = any(
        extract_value(
            r.get("content") or "", str(field), packet.get("facts", {}), source=r
        )[0]
        is not None
        and extract_value(
            r.get("content") or "", str(field), packet.get("facts", {}), source=r
        )[1]
        != "approximate_duration"
        for r in operative
    )
    operative_ids = {r.get("id") for r in operative}
    result = []
    for record in public.get("evidence", []):
        if not isinstance(record, Mapping):
            continue
        if field not in record.get("fields", []):
            continue
        if potential_entities and not (
            potential_entities & set(record.get("entity_ids", []))
        ):
            continue
        content = record.get("content")
        if isinstance(content, str) and _origin(record) != "dispatcher_owned":
            # Broad metadata scope alone does not make an unrelated report an
            # indispensable receiving/duration fact. Unknown released prose
            # with operational vocabulary remains conservatively relevant.
            vocabulary = (
                r"\b(?:service|unload(?:ing)?|duration|minutes?|mins?|allowance|plan(?:ning)?)\b"
                if field == "service_duration"
                else r"\b(?:receiv(?:e|ing)|unload(?:ing)?|pallet|start|begin|open|clos(?:e|ing)|finish|window|delivery|dock|bay)\b|\d{1,2}:\d{2}"
            )
            if not re.search(vocabulary, content, re.IGNORECASE):
                continue
        if record.get("id") in superseded:
            continue
        if (
            isinstance(record.get("content"), str)
            and relative_scope(dict(record), dict(packet)) is False
            # Released receiver provenance explains lack of current support
            # even when textual validity excludes the target. It does not
            # grant operative eligibility or require unrelated confirmation.
            and not (
                _available_state(record, str(packet.get("decision_time", "")))
                == "released"
                and record.get("source_type") in KNOWN_NON_DISPATCHER
            )
        ):
            continue
        if decisive and record.get("id") not in operative_ids:
            continue
        # Keep expired/future lifecycle records in the authority view. Their
        # current eligibility is handled by runtime admission; their source
        # origin still determines which party could confirm or explain them.
        result.append(record)
    return result


def _approximate_duration_origin(records: list[Mapping[str, Any]]) -> list[str]:
    qualifier = re.compile(
        r"\b(?:about|approximately|approx\.?|roughly|around|estimated?|estimate|circa)\b|~|\+\s*/\s*-",
        re.IGNORECASE,
    )
    return [
        str(record.get("id"))
        for record in records
        if record.get("source_type") != DISPATCHER
        and isinstance(record.get("content"), str)
        and qualifier.search(record["content"])
    ]


def _accessible_for_slot(
    slot: str,
    packet: Mapping[str, Any],
    output: Any,
    records: list[Mapping[str, Any]],
) -> tuple[list[bool | None], list[dict[str, Any]]]:
    field = packet.get("field")
    decision_time = str(packet.get("decision_time", ""))
    facts: list[dict[str, Any]] = []

    def fact(
        kind: str, value: bool | None, refs: list[Mapping[str, Any]]
    ) -> list[bool | None]:
        origins = sorted({_origin(r) for r in refs})
        availability = sorted({_available_state(r, decision_time) for r in refs})
        facts.append(
            {
                "kind": kind,
                "origin": origins
                or [
                    "dispatcher_manifest_scope"
                    if kind == "entity_lookup"
                    else "dispatcher_booked_stop_planning_role"
                    if kind == "planning_service_time_allowance"
                    else "unspecified"
                ],
                "record_ids": sorted(
                    str(r.get("id")) for r in refs if r.get("id") is not None
                ),
                "availability": availability,
                "status": "reachable"
                if value is True
                else "inaccessible"
                if value is False
                else "unknown",
            }
        )
        return [value]

    if slot == "entity":
        # The common channel may identify the booked stop/order or resolve a
        # manifest alias. It may not invent an identity for an unknown sender.
        entities = packet.get("entities", [])
        from .reason_predicates import plausible_entities

        mentions_manifest_entity = bool(plausible_entities(packet))
        if packet.get("target_entity"):
            value: bool | None = False  # already known; no missing fact remains
        elif mentions_manifest_entity:
            value = True
        elif entities:
            value = False  # unknown sender/name is outside the manifest scope
        else:
            value = None  # no public manifest context to classify the request
        return fact("booked_stop_or_manifest_alias", value, []), facts

    if slot == "authoritative_value":
        from .reason_predicates import detected_predicates

        causes = detected_predicates(output, packet)
        approximate = _approximate_duration_origin(records)
        if field == "service_duration":
            # The bounded runtime's specific approximation cause routes to an
            # explicit dispatcher planning allowance. Other source conflicts
            # remain source-origin facts below; record count is not conflict.
            if (
                causes.intersection(
                    {
                        "APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE",
                        "DISPATCHER_VALUE_UNAVAILABLE",
                    }
                )
                or approximate
            ):
                value = True
                kind = "planning_service_time_allowance"
            elif "ELIGIBLE_EVIDENCE_CONFLICT" in causes:
                value = False
                kind = "competing_source_values"
            else:
                value = None
                kind = "duration_fact_not_classified"
            return fact(kind, value, records), facts
        if records and all(_origin(r) == "dispatcher_owned" for r in records):
            # The common profile authorizes an explicit dispatcher planning
            # allowance for service duration. Other fields may be explained or
            # confirmed as dispatcher-owned instructions, but are not given a
            # general authoritative-value channel.
            return fact("non_duration_authoritative_value", False, records), facts
        return fact("non_dispatcher_value_authority", False, records), facts

    if slot in DISPATCHER_ONLY_SLOTS:
        # The dispatcher can answer only about its own issued/withdrawn
        # instructions and own booked-run facts. Unverified metadata does not
        # establish source ownership; receiver approval is outside its reach.
        if not records:
            return fact("dispatcher_owned_record_needed", None, []), facts
        values: list[bool | None] = []
        for record in records:
            origin = _origin(record)
            release = _available_state(record, decision_time)
            value = (
                True
                if origin == "dispatcher_owned" and release == "released"
                else None
                if origin == "dispatcher_owned" and release == "unknown"
                else False
            )
            values.extend(fact(slot, value, [record]))
        return values, facts

    if slot == "field":
        return fact("unsupported_field_definition", False, []), facts

    return fact("unrecognized_slot", None, records), facts


def assess(
    packet: Mapping[str, Any], output: Any, slots: list[str] | None = None
) -> dict[str, Any]:
    """Assess every requested slot against the public packet and policy.

    ``None`` is retained as unknown and omitted from the validator map, so the
    validator reports an authority-qualification deficiency. It is never
    silently treated as reachable or inaccessible.
    """
    from .output_contract import normalize_output

    normalized = normalize_output(output)
    requested = slots if slots is not None else normalized.get("missing_slots", [])
    from .reason_predicates import detected_predicates

    requested = list(requested)
    original_slots = set(requested)
    causes = detected_predicates(output, packet)
    groups = {
        "ENTITY_UNRESOLVED": ("entity",),
        "PERMISSION_IS_NOT_A_LOWER_BOUND": ("interpretation", "authoritative_value"),
        "APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE": ("authoritative_value",),
        "SUPPORT_EXPIRED": ("supporting_evidence", "confirmation"),
        "SUPPORT_UNVERIFIED": ("confirmation", "supporting_evidence"),
        "SUPPORT_UNRELEASED": ("supporting_evidence", "confirmation"),
        "DISPATCHER_DATE_UNAVAILABLE": ("effective_interval",),
        "DISPATCHER_VALUE_UNAVAILABLE": ("authoritative_value",),
    }
    missing = []
    if normalized.get("action") in {"clarify", "insufficient"}:
        for cause, alternatives in groups.items():
            if cause in causes and not original_slots.intersection(alternatives):
                missing.append(alternatives[0])
        requested = sorted(set(requested) | set(missing))
    records = _relevant_records(packet)
    assessment: dict[str, bool | list[bool]] = {}
    fact_details: dict[str, list[dict[str, Any]]] = {}
    unknown_slots: list[str] = []
    for slot in requested:
        values, details = _accessible_for_slot(slot, packet, output, records)
        fact_details[slot] = details
        if any(value is None for value in values):
            unknown_slots.append(slot)
            continue
        known_values = [v for v in values if isinstance(v, bool)]
        assessment[slot] = known_values[0] if len(known_values) == 1 else known_values
    return {
        "assessment": assessment,
        "unreported_indispensable_slots": sorted(set(missing)),
        "facts": fact_details,
        "unknown_slots": sorted(set(unknown_slots)),
        "qualification": "unknown_policy" if unknown_slots else "assessed",
    }
