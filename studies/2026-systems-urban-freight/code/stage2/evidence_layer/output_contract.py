"""Shared, case-label-blind output normalization and shape qualification.

This module defines a common interface for S1, S2 and S3.  It does not decide
whether cited prose entails a proposal and it never reads case annotations.
Reason normalization is a finite public-vocabulary adapter; unknown prose is
preserved as text but is not treated as semantic truth.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping
from typing import Any

FIELDS = {
    "receiving_window_start": "Europe/Rome local time",
    "receiving_window_end": "Europe/Rome local time",
    "service_duration": "minutes",
}

# Public slots describe the fact needed, not a preferred gold annotation.
SLOTS = {
    "entity",
    "effective_interval",
    "authoritative_value",
    "confirmation",
    "supporting_evidence",
    "interpretation",
    "interpretation_or_confirmation",  # preserved legacy compound slot
    "field",
}

# Adopted simulated_dispatcher authority. Reachability is an available channel
# for every episode; answerability is limited to these public slot capabilities.
DEFAULT_PROFILE = {
    "channel": "simulated_dispatcher",
    "reachable": True,
    "answerable_slots": frozenset(
        {
            "entity",
            "effective_interval",
            "authoritative_value",
            "confirmation",
            "supporting_evidence",
            "interpretation",
        }
    ),
}

# Existing runtime and admission strings are normalized to broad semantic
# classes. This vocabulary intentionally does not contain scorer/gold codes.
REASON_CLASSES = {
    "entity_unresolved",
    "field_unsupported",
    "evidence_absent",
    "evidence_conflict",
    "interpretation_needed",
    "scope_unresolved",
    "value_unsupported",
    "confirmation_needed",
    "proposal_invalid",
    "other_known",
}

_REASON_MAP = {
    "ambiguous_entity": "entity_unresolved",
    "missing_entity": "entity_unresolved",
    "entity_unresolved": "entity_unresolved",
    "unknown_entity": "entity_unresolved",
    "target_scope": "entity_unresolved",
    "unsupported_field": "field_unsupported",
    "no_eligible_evidence": "evidence_absent",
    "no_supported_value": "evidence_absent",
    "conflicting_evidence": "evidence_conflict",
    "structured_grammar_conflict": "evidence_conflict",
    "parsed_fact_contradiction": "evidence_conflict",
    "ambiguous_values": "interpretation_needed",
    "parser_noncoverage": "interpretation_needed",
    "interpretation_needed": "interpretation_needed",
    "unconfirmed_language": "confirmation_needed",
    "needed_fact_outside_dispatcher_scope": "value_unsupported",
    "start_permission_not_bound": "interpretation_needed",
    "approximate_duration": "value_unsupported",
    "approximate_duration_needs_planning_allowance": "value_unsupported",
    "estimate_requires_planning_allowance": "value_unsupported",
    "permission_not_lower_bound": "interpretation_needed",
    "start_permission_is_not_a_lower_bound": "interpretation_needed",
    "unreleased_support": "value_unsupported",
    "unverified_support": "value_unsupported",
    "expired_support": "value_unsupported",
    "support_unreleased_or_unverified": "value_unsupported",
    "support_expired": "value_unsupported",
    "support_unreleased": "value_unsupported",
    "support_unverified": "value_unsupported",
    "support_not_currently_usable": "value_unsupported",
    "missing_dispatch_value": "evidence_absent",
    "missing_dispatch_date": "scope_unresolved",
    "missing_dispatch_value_or_date": "evidence_absent",
    "dispatcher_value_unavailable": "evidence_absent",
    "dispatcher_date_unavailable": "scope_unresolved",
    "dispatcher_value_or_date_unavailable": "evidence_absent",
    "eligible_evidence_conflict": "evidence_conflict",
    "permission_is_not_a_lower_bound": "interpretation_needed",
    "missing_entity_and_permission_not_lower_bound": "entity_unresolved",
    "invalid_time": "interpretation_needed",
    "missing_relative_date_anchor": "scope_unresolved",
    "relative_date_scope": "scope_unresolved",
    "target_effective_time": "scope_unresolved",
    "validity_scope": "scope_unresolved",
    "ineligible_or_invalid_citation": "value_unsupported",
    "schema_or_domain_shape": "proposal_invalid",
    "rejected_proposal:target_scope": "entity_unresolved",
    "rejected_proposal:target_effective_time": "scope_unresolved",
    "rejected_proposal:relative_date_scope": "scope_unresolved",
    "rejected_proposal:validity_scope": "scope_unresolved",
    "rejected_proposal:structured_grammar_conflict": "evidence_conflict",
    "rejected_proposal:parsed_fact_contradiction": "evidence_conflict",
    "rejected_proposal:ineligible_or_invalid_citation": "value_unsupported",
    "rejected_proposal:schema_or_domain_shape": "proposal_invalid",
    "rejected_proposal:needed_fact_outside_dispatcher_scope": "value_unsupported",
    "unique_eligible_value": "other_known",
    "common_shape_only": "other_known",
    "structural_provenance_checks_only": "other_known",
    "nonmutating_decision_not_semantically_verified": "other_known",
}

_SLOT_ALIASES = {
    "delivery_day": "effective_interval",
    "date": "effective_interval",
    "time_window": "effective_interval",
    "scope": "effective_interval",
    "value": "authoritative_value",
    "duration": "authoritative_value",
    "opening_time": "authoritative_value",
    "source": "supporting_evidence",
    "evidence": "supporting_evidence",
    "authority": "confirmation",
    "receiver_approval": "confirmation",
    "interpretation_or_confirmation": "interpretation_or_confirmation",
}


def _clean_reason(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value.strip().casefold()) or None


def _slots(output: Mapping[str, Any]) -> list[str]:
    raw = output.get("missing_slots")
    if raw is None:
        raw = output.get("missing_slot")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        slot = _SLOT_ALIASES.get(item.strip().casefold(), item.strip().casefold())
        if slot:
            # Preserve unknown and compound slots for explicit qualification;
            # silently dropping them would erase what the actor requested.
            result.append(slot)
    return sorted(set(result))


def normalize_output(output: Any) -> dict[str, Any]:
    """Return the shared representation without asserting semantic correctness."""
    if not isinstance(output, Mapping):
        return {
            "case_id": None,
            "action": None,
            "reason_text": None,
            "reason_class": None,
            "missing_slots": [],
            "evidence_refs": None,
        }
    action = output.get("action")
    action = action.casefold() if isinstance(action, str) else None
    reason_text = _clean_reason(output.get("reason_code", output.get("reason")))
    from .reason_predicates import normalize_reason

    reason_class = normalize_reason(reason_text)
    if reason_class is None and reason_text is not None:
        reason_class = _REASON_MAP.get(reason_text)
    return {
        "case_id": output.get("case_id"),
        "action": action,
        "reason_text": reason_text,
        "reason_class": reason_class,
        "missing_slots": _slots(output),
        "evidence_refs": output.get("evidence_refs"),
    }


def _valid_datetime_pair(start: Any, end: Any) -> bool:
    if not isinstance(start, str) or not isinstance(end, str):
        return False
    try:
        left, right = dt.datetime.fromisoformat(start), dt.datetime.fromisoformat(end)
    except ValueError:
        return False
    if left.tzinfo is None or right.tzinfo is None:
        return False
    return left < right


def _numeric_refs(refs: Any) -> bool:
    # “Numeric” means source-record identifiers, not free-text quotations.
    # The source record ID is the stable reference; quotes are provenance detail.
    return bool(
        isinstance(refs, list)
        and refs
        and all(
            isinstance(ref, Mapping)
            and isinstance(ref.get("id"), str)
            and bool(ref["id"].strip())
            and isinstance(ref.get("quote"), str)
            and bool(ref["quote"].strip())
            for ref in refs
        )
    )


def validate_output(
    output: Any,
    *,
    channel_profile: Mapping[str, Any] = DEFAULT_PROFILE,
    authority_assessment: Mapping[str, bool | list[bool] | tuple[bool, ...]]
    | None = None,
    packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate shared output shape and referral channel/authority consistency.

    ``authority_assessment`` is common-policy context, not actor output. It must
    assess every indispensable fact requested under each missing slot. A bool
    means one fact; a list/tuple preserves multiple facts under one slot. Missing
    assessments are qualification deficiencies. True cannot add capabilities
    beyond the adopted dispatcher profile. This is policy qualification, not
    source-truth adjudication.
    """
    n = normalize_output(output)
    errors: list[str] = []
    if not isinstance(output, Mapping):
        errors.append("output_must_be_object")
        return {
            **n,
            "valid": False,
            "errors": errors,
            "provenance_diagnostic": "not_applicable",
        }

    action = n["action"]
    if action not in {"update", "retain", "clarify", "insufficient"}:
        errors.append("invalid_action")
    if not isinstance(n["case_id"], (str, int)) or isinstance(n["case_id"], bool):
        errors.append("missing_case_id")

    provenance = "optional_for_referral"
    if action in {"update", "retain"}:
        if (
            not isinstance(output.get("entity_id"), str)
            or not output["entity_id"].strip()
        ):
            errors.append("missing_entity_id")
        field = output.get("field")
        if field not in FIELDS:
            errors.append("invalid_field")
        else:
            unit = output.get("unit")
            if unit != FIELDS[field]:
                errors.append("unit_mismatch")
            value = output.get("value")
            if field == "service_duration":
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not 0 < value <= 240
                ):
                    errors.append("invalid_numeric_value")
            elif not isinstance(value, str) or not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", value
            ):
                errors.append("invalid_clock_value")
        if not _valid_datetime_pair(
            output.get("effective_from"), output.get("effective_until")
        ):
            errors.append("invalid_effective_interval")
        provenance = (
            "complete" if _numeric_refs(n["evidence_refs"]) else "missing_or_malformed"
        )
        if provenance != "complete":
            errors.append("numeric_evidence_refs_required")
    elif action in {"clarify", "insufficient"}:
        if not n["missing_slots"]:
            errors.append("referral_missing_slots")
        if any(slot not in SLOTS for slot in n["missing_slots"]):
            errors.append("unknown_missing_slot")
        if n["reason_class"] is None:
            errors.append("reason_not_in_public_vocabulary")
        reason_check = None
        if packet is None:
            errors.append("reason_packet_required")
        else:
            from .reason_predicates import qualify_reason

            reason_check = qualify_reason(output, packet)
            errors.extend(reason_check["errors"])
        profile_reachable = channel_profile.get("reachable") is True
        answerable = set(channel_profile.get("answerable_slots", ()))
        assessments: list[bool] = []
        if authority_assessment is None:
            errors.append("authority_assessment_required")
        elif not isinstance(authority_assessment, Mapping):
            errors.append("invalid_authority_assessment")
        else:
            for slot in n["missing_slots"]:
                if slot not in authority_assessment:
                    errors.append("authority_assessment_incomplete")
                    continue
                assessment = authority_assessment[slot]
                facts = (
                    assessment
                    if isinstance(assessment, (list, tuple))
                    else [assessment]
                )
                if not facts or any(not isinstance(value, bool) for value in facts):
                    errors.append("invalid_authority_assessment")
                    continue
                assessments.extend(facts)
        requested = set(n["missing_slots"])
        all_reachable = (
            profile_reachable
            and bool(requested)
            and requested <= answerable
            and bool(assessments)
            and all(assessments)
            and not any(
                e.startswith("authority_assessment")
                or e == "invalid_authority_assessment"
                for e in errors
            )
        )
        some_known_inaccessible = any(value is False for value in assessments)
        if (
            action == "clarify"
            and authority_assessment is not None
            and not all_reachable
        ):
            errors.append("clarify_requires_all_indispensable_facts_answerable")
        if action == "insufficient" and all_reachable:
            errors.append("insufficient_inconsistent_with_answerable_facts")
        if (
            action == "insufficient"
            and authority_assessment is not None
            and not all_reachable
            and not some_known_inaccessible
        ):
            errors.append("insufficient_requires_known_inaccessible_fact")
    return {
        **n,
        "valid": not errors,
        "errors": errors,
        "provenance_diagnostic": provenance,
        "reason_qualification": reason_check
        if action in {"clarify", "insufficient"}
        else None,
    }
