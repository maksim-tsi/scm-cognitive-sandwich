"""Bounded deterministic S1 and partial evidence-admission gate.

Input is a raw packet only. No file loader, gold labels, LLM, network or solver.
The gate checks structural/eligible/parsed-fact contradictions, NOT general
natural-language entailment. Unparsed prose remains semantically unchecked.
"""

from __future__ import annotations

import copy
import datetime as dt
import decimal
import hashlib
import json
import re
import unicodedata
from typing import Any

FIELDS = {"receiving_window_start", "receiving_window_end", "service_duration"}
AUTHORITIES = {"receiver_confirmation", "signed_schedule", "dispatcher_instruction"}
TIME = r"([0-2]?\d:[0-5]\d)"
APPROXIMATE = re.compile(
    r"\b(?:about|approximately|approx\.?|roughly|around|estimated?|estimate|"
    r"circa|more\s+or\s+less)\b|~|\+\s*/\s*-",
    re.IGNORECASE,
)


def instant(text: str) -> dt.datetime:
    value = dt.datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise ValueError("UTC offset is mandatory")
    return value.astimezone(dt.UTC)


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def clock_words(text: str) -> str:
    hours = {
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }
    names = "|".join(hours)
    text = re.sub(
        r"half past (" + names + r")\b", lambda m: f"{hours[m[1]]:02}:30", text
    )
    text = re.sub(
        r"quarter past (" + names + r")\b", lambda m: f"{hours[m[1]]:02}:15", text
    )
    text = re.sub(
        r"quarter to (" + names + r")\b", lambda m: f"{hours[m[1]] - 1:02}:45", text
    )
    text = re.sub(
        r"\b(" + names + r") (thirty|fifteen|forty-five)\b",
        lambda m: (
            f"{hours[m[1]]:02}:{ {'thirty': 30, 'fifteen': 15, 'forty-five': 45}[m[2]]:02}"
        ),
        text,
    )
    return text


def parse_clock_periods(text: str) -> str:
    def convert(match: re.Match[str]) -> str:
        hour, minute, period = int(match[1]), int(match[2]), match[3]
        if not 1 <= hour <= 12:
            return "INVALID_CLOCK"
        return f"{hour % 12 + (12 if period == 'pm' else 0):02}:{minute:02}"

    return re.sub(r"\b(\d{1,2}):([0-5]\d)\s*([ap]m)\b", convert, text)


def relative_scope(record: dict[str, Any], packet: dict[str, Any]) -> bool | None:
    words = re.findall(
        r"\b(today|tomorrow|yesterday)\b", normalized(record.get("content") or "")
    )
    if not words:
        return True
    if not record.get("published_at"):
        return None
    source_date = dt.datetime.fromisoformat(record["published_at"]).date()
    target_date = dt.datetime.fromisoformat(packet["effective_time"]).date()
    return all(
        source_date
        + dt.timedelta(days={"today": 0, "tomorrow": 1, "yesterday": -1}[word])
        == target_date
        for word in words
    )


def packet_hash(packet: Any) -> str:
    try:
        payload = json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()
    except (TypeError, ValueError):
        # Invalid model output still receives an auditable attempt hash instead
        # of crashing before the failed-attempt record can be emitted.
        payload = repr(packet).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def released_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Redact unreleased content while preserving public lifecycle metadata.

    Keeping records in place prevents an unavailable value from becoming
    indistinguishable from an absent source. Applying this function twice has
    the same result as applying it once.
    """
    result = copy.deepcopy(packet)
    now = instant(packet["decision_time"])
    public_lifecycle_fields = {
        "id",
        "source_type",
        "verified",
        "available_at",
        "published_at",
        "effective_from",
        "effective_until",
        "entity_ids",
        "fields",
        "supersedes",
        "revoked_at",
        "content",
    }
    released = []
    for record in result.get("evidence", []):
        if not isinstance(record, dict):
            released.append(record)
            continue
        record = {
            key: value
            for key, value in record.items()
            if key in public_lifecycle_fields
        }
        available_at = record.get("available_at")
        try:
            disclose = isinstance(available_at, str) and instant(available_at) <= now
        except (TypeError, ValueError):
            disclose = False
        record["content"] = record.get("content") if disclose else None
        released.append(record)
    result["evidence"] = released
    return result


def resolve_entity(packet: dict[str, Any]) -> tuple[str | None, str | None]:
    target = packet.get("target_entity")
    ids = {e["id"] for e in packet["entities"]}
    if target:
        return (target, None) if target in ids else (None, "unknown_entity")
    text = normalized(packet["message"])
    hits = set()
    for entity in packet["entities"]:
        for alias in [entity["id"], entity["name"], *entity.get("aliases", [])]:
            if re.search(r"(?<!\w)" + re.escape(normalized(alias)) + r"(?!\w)", text):
                hits.add(entity["id"])
    return (
        (next(iter(hits)), None)
        if len(hits) == 1
        else (None, "ambiguous_entity" if hits else "missing_entity")
    )


def eligible_records(
    packet: dict[str, Any], entity: str
) -> tuple[list[dict[str, Any]], list[str]]:
    now = instant(packet["decision_time"])
    effective = instant(packet["effective_time"])
    kept, rejected = [], []
    for r in packet["evidence"]:
        if r.get("source_type") not in AUTHORITIES or r.get("verified") is not True:
            rejected.append(r["id"])
            continue
        if not r.get("available_at") or instant(r["available_at"]) > now:
            rejected.append(r["id"])
            continue
        if entity not in r.get("entity_ids", []) or packet["field"] not in r.get(
            "fields", []
        ):
            rejected.append(r["id"])
            continue
        if r.get("revoked_at") and instant(r["revoked_at"]) <= now:
            rejected.append(r["id"])
            continue
        if not r.get("effective_from") or not r.get("effective_until"):
            rejected.append(r["id"])
            continue
        if (
            not instant(r["effective_from"])
            <= effective
            < instant(r["effective_until"])
        ):
            rejected.append(r["id"])
            continue
        kept.append(r)
    superseded = {key for r in kept for key in r.get("supersedes", [])}
    return [r for r in kept if r["id"] not in superseded], rejected


def extract_value(
    content: str,
    field: str,
    facts: dict[str, bool] | None = None,
    *,
    current_value: Any = None,
    source: dict[str, Any] | None = None,
) -> tuple[Any, str]:
    """Frozen finite grammar. Return noncoverage explicitly, never guessed gold."""
    from .conditional_instructions import select_branch

    # Attribution in an authenticated receiver record is not third-party
    # hearsay. Match the complete bounded wrapper; never discard an arbitrary
    # uncertainty, negation, condition or reporting prefix/suffix.
    if (
        source
        and source.get("source_type") == "receiver_confirmation"
        and source.get("verified") is True
    ):
        direct = re.fullmatch(
            r"""\s*(?:the\s+)?receiver\s+(?:says?|said|told\s+us)\s*[:,]?\s*["“](.*?)["”]\s*\.?\s*""",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        if direct:
            content = direct[1]
        else:
            direct = re.fullmatch(
                r"(?P<prefix>\s*(?:[A-Za-z]+ receiving desk\.\s*|at [^,:]+,\s*)?)(?:the\s+)?receiver\s+(?:says?|said)\s*:\s*(?P<instruction>.+)",
                content,
                re.IGNORECASE | re.DOTALL,
            )
            if direct:
                # Remove only authenticated attribution. A neutral location
                # prefix and scope trailer remain in the guarded instruction.
                content = direct["prefix"] + direct["instruction"]
    branch = select_branch(content, facts)
    # Retain the existing bounded postfix-guard grammar (instruction IF fact).
    # Prefix conditional forms use the shared branch selector in every caller.
    condition_start = branch.get("condition_start")
    normalized_content = unicodedata.normalize("NFKC", content)
    prefix = (
        normalized_content[:condition_start] if isinstance(condition_start, int) else ""
    )
    postfix_guard = bool(
        re.search(r"\d{1,2}:\d{2}|\d+\s*(?:minutes?|mins?)\b", prefix, re.IGNORECASE)
    )
    if branch["status"] != "no_condition" and not postfix_guard:
        if branch["status"] != "selected":
            return None, "unresolved_condition"
        content = branch["selected_text"]
    text = parse_clock_periods(clock_words(normalized(content)))
    text = re.sub(r"\b(?:noon|midday)\b", "12:00", text)
    if "INVALID_CLOCK" in text:
        return None, "invalid_time"
    if re.search(
        r"\b(might|maybe|perhaps|possibly|uncertain|rumou?r|tentative|draft|unconfirmed|suggested)\b",
        text,
    ):
        return None, "unconfirmed_language"
    if any(
        phrase in text
        for phrase in [
            "i heard",
            "someone said",
            "reportedly",
            "not approved",
            "not confirmed",
            "has not confirmed",
            "proposed but",
        ]
    ):
        return None, "unconfirmed_language"
    if re.search(r"\b(heard|says?|said|told)\b", text):
        return None, "reported_instruction_requires_confirmation"
    conditions = {
        "booking is confirmed": "booking_confirmed",
        "receiver is present": "receiver_present",
        "forklift is available": "forklift_available",
    }
    if re.search(r"\b(if|unless|provided|only when)\b", text):
        matches = [
            (phrase, key) for phrase, key in conditions.items() if phrase in text
        ]
        if len(matches) != 1:
            return None, "unresolved_condition"
        _phrase, key = matches[0]
        required = not bool(re.search(r"\bunless\b", text))
        if (facts or {}).get(key) is not required:
            return None, "unresolved_condition"
        text = re.sub(r"\b(?:only\s+)?(?:if|unless|provided|only when)\b.*", "", text)
    text = re.sub(r"\b(today|tomorrow|yesterday)\b", "", text)
    text = re.sub(r"\s+", " ", text)
    # Explicit correction structure; negated old values are not candidates.
    text = re.sub(r"\bnot\s+\d{1,2}:\d{2}\s+but\s+", "", text)
    # Bounded unloading prohibitions establish an earliest start. Rewrite only
    # these complete modal/verb relations before the generic negation guard.
    if field == "receiving_window_start":
        text = re.sub(
            r"\b(?:the\s+first\s+pallet|unloading)\s+(?:must\s+not\s+(?:come\s+off|begin|start)\s+before|cannot\s+(?:come\s+off|begin|start)\s+until)\s+(?:at\s+)?(?=\d{1,2}:\d{2})",
            "not before ",
            text,
        )
    # Unsupported negation is noncoverage, rather than a positive reading of
    # e.g. "will not receive until 08:00" as a receiving END at 08:00.
    negation_probe = re.sub(
        r"\b(?:not before|no earlier than|no later than)\b", "", text
    )
    negation_probe = re.sub(r"\bnot\s+\d+\s+minutes?\s+but\s+", "", negation_probe)
    if re.search(
        r"\b(?:not|never|no|won't|cannot|can't|isn't|doesn't)\b", negation_probe
    ):
        return None, "negation_noncoverage"
    # A positive retention instruction with one explicit clock value retains
    # that source-supported value, not blindly the packet's current scalar.
    if field in {"receiving_window_start", "receiving_window_end"} and re.search(
        r"\b(?:keep|retain|remains?|stays?)\b", text
    ):
        clocks = set(re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", text))
        if len(clocks) == 1:
            clock = next(iter(clocks))
            hour, minute = clock.split(":")
            return f"{int(hour):02}:{minute}", "parsed"
    if (
        field == "service_duration"
        and current_value is not None
        and re.search(
            r"\b(?:keep|retain|continue with)\s+(?:the\s+)?(?:regular|current|existing|ordinary)\s+(?:plan|schedule)\b",
            text,
        )
        and (
            APPROXIMATE.search(text)
            or not re.search(r"\d+\s*(?:minutes?|mins?|hours?)", text)
        )
    ):
        return current_value, "explicit_keep_plan"
    values: set[Any]
    if field == "service_duration":
        if "quarter of an hour" in text:
            return 15.0, "parsed_idiom"
        if "half an hour" in text:
            return 30.0, "parsed_idiom"
        for word, value in {
            "five": 5,
            "eight": 8,
            "ten": 10,
            "twelve": 12,
            "fifteen": 15,
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "sixty": 60,
        }.items():
            text = re.sub(
                r"\b" + word + r"(?=\s+(?:minutes?|mins?)\b)", str(value), text
            )
        text = re.sub(r"\bnot\s+\d+\s+minutes?\s+but\s+", "", text)
        matches = re.findall(
            r"(\d+(?:[.,]\d+)?)\s*(minutes?|mins?|hours?|hrs?)\b", text
        )
        values = {
            float(
                decimal.Decimal(n.replace(",", "."))
                * (60 if u.startswith(("hour", "hr")) else 1)
            )
            for n, u in matches
        }
    else:
        if field == "receiving_window_start":
            # A permission is not a lower bound. Keep it out of the scalar
            # earliest-start interpretation; callers can route the unresolved
            # condition through the shared channel policy below.
            if re.search(
                r"\b(?:can|may|could|(?:is|are) allowed to|(?:is|are) permitted to)\s+(?:start|begin|open|receive|unload|come off)\b|\bpermission to\s+(?:start|begin|receive|unload)",
                text,
            ) and not re.search(r"\b(?:not before|no earlier than)\s+" + TIME, text):
                return None, "start_permission_not_bound"
            patterns = [
                r"(?:receiving\s+(?:starts?|opens?)|opens?|start(?:s)?|not before|no earlier than|from|after)\s+(?:at\s+)?"
                + TIME
            ]
        else:
            patterns = [
                r"(?:receiving\s+(?:ends?|closes?)|closes?|until|by|no later than|finish(?:ed)? by|ends?)\s+(?:at\s+)?"
                + TIME
            ]
        values = set()
        for pattern in patterns:
            for h in re.findall(pattern, text):
                hour, minute = map(int, h.split(":"))
                if hour > 23:
                    return None, "invalid_time"
                values.add(f"{hour:02}:{minute:02}")
    if len(values) == 1:
        if field == "service_duration" and APPROXIMATE.search(text):
            return next(iter(values)), "approximate_duration"
        return next(iter(values)), "parsed"
    return None, "ambiguous_values" if values else "parser_noncoverage"


def decision(
    action: str, reason: str, packet: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    return {"case_id": packet["case_id"], "action": action, "reason": reason, **kwargs}


def normalize_common_output(packet: dict[str, Any], output: Any) -> dict[str, Any]:
    """Apply the single packet-aware output contract to every lane/action.

    ``reason_code`` is a legacy spelling accepted at the boundary. Internally
    the normalized proposal has one ``reason`` field. Conflicting dual fields
    are rejected; all other fields are passed through without repair.
    """
    from collections.abc import Mapping

    from .authority_closure import assess as close_authority
    from .output_contract import validate_output
    from .reason_predicates import normalize_reason

    if not isinstance(output, Mapping):
        canonical = output
        closure = close_authority(packet, output)
        validation = validate_output(
            output, packet=packet, authority_assessment=closure["assessment"]
        )
        return {
            "output": canonical,
            "valid": False,
            "errors": list(validation["errors"]),
            "validation": validation,
            "authority_closure": closure,
        }

    canonical = copy.deepcopy(dict(output))
    reason = canonical.get("reason")
    reason_code = canonical.get("reason_code")
    shape_errors: list[str] = []
    if "reason" in canonical and "reason_code" in canonical:
        normalized_reason = normalize_reason(reason)
        normalized_code = normalize_reason(reason_code)
        same_raw = (
            isinstance(reason, str)
            and isinstance(reason_code, str)
            and reason == reason_code
        )
        same_semantic = (
            normalized_reason is not None
            and normalized_code is not None
            and normalized_reason == normalized_code
        )
        if not (same_raw or same_semantic):
            shape_errors.append("conflicting_reason_fields")
        canonical["reason"] = reason_code
        del canonical["reason_code"]
    elif reason_code is not None:
        canonical["reason"] = reason_code
        del canonical["reason_code"]

    closure = close_authority(packet, canonical)
    try:
        validation = validate_output(
            canonical,
            packet=packet,
            authority_assessment=closure["assessment"],
        )
    except (TypeError, ValueError, KeyError) as error:
        # Malformed nested values (for example, a list where field is scalar)
        # must fail closed even if the downstream validator cannot hash them.
        validation = {
            "valid": False,
            "errors": ["malformed_unhashable_or_invalid_output_value"],
            "validator_error_type": type(error).__name__,
        }
    errors = list(validation["errors"])
    errors.extend(shape_errors)
    if closure.get("unreported_indispensable_slots"):
        errors.append("unreported_indispensable_facts")

    action = canonical.get("action")
    if not isinstance(action, str) or action not in {
        "update",
        "retain",
        "clarify",
        "insufficient",
    }:
        errors.append("invalid_action_spelling")
    if canonical.get("case_id") != packet.get("case_id"):
        errors.append("case_id_mismatch")
    if isinstance(action, str) and action in {"update", "retain"}:
        entity = canonical.get("entity_id")
        field = canonical.get("field")
        known_entities = {
            record.get("id")
            for record in packet.get("entities", [])
            if isinstance(record, dict)
        }
        if not isinstance(entity, str) or entity not in known_entities:
            errors.append("entity_not_in_packet")
        if (
            not isinstance(field, str)
            or field != packet.get("field")
            or field not in FIELDS
        ):
            errors.append("field_packet_mismatch")
        if (
            action == "retain"
            and isinstance(entity, str)
            and isinstance(field, str)
            and canonical.get("value")
            != packet.get("current_state", {}).get(entity, {}).get(field)
        ):
            errors.append("retain_value_must_match_current_state")
        try:
            if not (
                instant(canonical["effective_from"])
                <= instant(packet["effective_time"])
                < instant(canonical["effective_until"])
            ):
                errors.append("target_effective_time_not_covered")
        except (KeyError, TypeError, ValueError):
            # The output validator reports malformed/missing intervals.
            pass

    # Keep a stable ordered error list while preserving the validator's own
    # diagnostics for review.
    errors = list(dict.fromkeys(errors))
    validation["errors"] = errors
    validation["valid"] = not errors
    return {
        "output": canonical,
        "valid": not errors,
        "errors": errors,
        "validation": validation,
        "authority_closure": closure,
    }


def is_physical_bound(content: str, field: str) -> bool:
    text = normalized(content)
    if field == "receiving_window_start":
        return bool(
            re.search(
                r"\b(?:not before|no earlier than|must not (?:begin|come off) before|cannot (?:begin|start|come off) until|earliest)\b",
                text,
            )
        )
    if field == "receiving_window_end":
        return bool(
            re.search(r"\b(?:by|no later than|must finish by|finish by)\b", text)
        )
    return False


def referral(
    packet: dict[str, Any], reason: str, slots: list[str], **kwargs: Any
) -> dict[str, Any]:
    """Choose a referral only from common packet-origin authority closure."""
    from .authority_closure import assess

    candidate = decision(
        "clarify", reason, packet, missing_slot=slots[0], missing_slots=slots, **kwargs
    )
    closure = assess(packet, candidate, slots)
    if closure["unreported_indispensable_slots"]:
        slots = sorted(set(slots) | set(closure["unreported_indispensable_slots"]))
        candidate["missing_slot"] = slots[0]
        candidate["missing_slots"] = slots
        closure = assess(packet, candidate, slots)
    values = [
        value
        for assessment in closure["assessment"].values()
        for value in (assessment if isinstance(assessment, list) else [assessment])
    ]
    if closure["unknown_slots"]:
        candidate["authority_qualification"] = "unknown_policy"
        candidate["authority_facts"] = closure["facts"]
        return candidate
    if values and all(values):
        candidate["channel"] = "simulated_dispatcher"
        candidate["authority_facts"] = closure["facts"]
        return candidate
    candidate["action"] = "insufficient"
    candidate["authority_facts"] = closure["facts"]
    return candidate


def s1(packet: dict[str, Any]) -> dict[str, Any]:
    """Same public data/normalization as admission; no hidden answer lookup."""
    packet = released_packet(packet)
    if packet["field"] not in FIELDS:
        return decision(
            "insufficient", "unsupported_field", packet, missing_slot="field"
        )
    entity, reason = resolve_entity(packet)
    if entity is None:
        from .reason_predicates import detected_predicates

        causes = detected_predicates({}, packet)
        if "PERMISSION_IS_NOT_A_LOWER_BOUND" in causes:
            reason = "missing_entity_and_permission_not_lower_bound"
        return referral(packet, str(reason), ["entity"])
    records, _ = eligible_records(packet, entity)
    from .reason_predicates import detected_predicates

    causes = detected_predicates({}, packet)
    if {"DISPATCHER_VALUE_UNAVAILABLE", "DISPATCHER_DATE_UNAVAILABLE"} <= causes:
        return referral(
            packet,
            "missing_dispatch_value_and_effective_date",
            ["authoritative_value", "effective_interval"],
            entity_id=entity,
        )
    if "DISPATCHER_DATE_UNAVAILABLE" in causes:
        return referral(
            packet, "missing_dispatch_date", ["effective_interval"], entity_id=entity
        )
    if "DISPATCHER_VALUE_UNAVAILABLE" in causes:
        return referral(
            packet, "missing_dispatch_value", ["authoritative_value"], entity_id=entity
        )
    if not records:
        if "SUPPORT_EXPIRED" in causes:
            return referral(
                packet, "expired_support", ["supporting_evidence"], entity_id=entity
            )
        return decision(
            "insufficient",
            "no_eligible_evidence",
            packet,
            entity_id=entity,
            missing_slot="supporting_evidence",
            missing_slots=["supporting_evidence"],
        )
    candidates, unresolved = [], []
    for record in records:
        scope = relative_scope(record, packet)
        if scope is not True:
            unresolved.append(
                "missing_relative_date_anchor"
                if scope is None
                else "relative_date_scope"
            )
            continue
        content = record.get("content") or ""
        value, status = extract_value(
            content,
            packet["field"],
            packet.get("facts", {}),
            current_value=packet["current_state"][entity][packet["field"]],
            source=record,
        )
        if status == "approximate_duration" or value is None:
            unresolved.append(status)
        else:
            candidates.append((value, record))
    values = {json.dumps(value) for value, _ in candidates}
    all_bounds = bool(candidates) and all(
        is_physical_bound(r.get("content") or "", packet["field"])
        for _v, r in candidates
    )
    if len(values) > 1 and all_bounds and packet["field"] == "receiving_window_start":
        # Independently applicable earliest-start bounds intersect at max.
        value = max(v for v, _ in candidates)
    elif len(values) > 1 and all_bounds and packet["field"] == "receiving_window_end":
        # Independently applicable completion deadlines intersect at min.
        value = min(v for v, _ in candidates)
    elif len(values) > 1:
        return referral(
            packet, "conflicting_evidence", ["authoritative_value"], entity_id=entity
        )
    # An independently supported scalar planning allowance resolves an
    # approximate observation; a supported start bound resolves mere permission.
    # Other unparsed instructions still block finite-grammar resolution.
    if candidates:
        unresolved = [
            status
            for status in unresolved
            if status not in {"approximate_duration", "start_permission_not_bound"}
        ]
    # Do not silently ignore an unparsed equally eligible record.
    if unresolved:
        status = unresolved[0]
        slot = (
            "authoritative_value"
            if status in {"approximate_duration", "start_permission_not_bound"}
            else (
                "effective_interval"
                if status in {"missing_relative_date_anchor", "relative_date_scope"}
                else "interpretation"
            )
        )
        return referral(packet, status, [slot], entity_id=entity)
    if not candidates:
        return decision(
            "insufficient",
            "no_supported_value",
            packet,
            entity_id=entity,
            missing_slot="supporting_evidence",
            missing_slots=["supporting_evidence"],
        )
    record = candidates[0][1]
    if len(values) > 1:
        matching = [r for v, r in candidates if v == value]
        record = matching[0]
    else:
        value = candidates[0][0]
    current = packet["current_state"][entity][packet["field"]]
    return decision(
        "retain" if current == value else "update",
        "unique_eligible_value",
        packet,
        entity_id=entity,
        field=packet["field"],
        value=value,
        unit="minutes"
        if packet["field"] == "service_duration"
        else "Europe/Rome local time",
        effective_from=record["effective_from"],
        effective_until=record["effective_until"],
        evidence_refs=[
            {"id": r["id"], "quote": r["content"]} for v, r in candidates if v == value
        ],
    )


def shape_valid(proposal: dict[str, Any], packet: dict[str, Any]) -> bool:
    return normalize_common_output(packet, proposal)["valid"]


def admission(packet: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    contract = normalize_common_output(packet, proposal)
    if not contract["valid"]:
        return {
            "admitted": False,
            "reason": "schema_or_domain_shape",
            "output_contract": contract["validation"],
            "authority_closure": contract["authority_closure"],
        }
    proposal = contract["output"]
    if proposal["action"] in {"clarify", "insufficient"}:
        return {
            "admitted": True,
            "reason": "nonmutating_decision_not_semantically_verified",
        }
    entity, _ = resolve_entity(packet)
    if (
        entity is None
        or entity != proposal["entity_id"]
        or packet["field"] != proposal["field"]
    ):
        return {"admitted": False, "reason": "target_scope"}
    if (
        not instant(proposal["effective_from"])
        <= instant(packet["effective_time"])
        < instant(proposal["effective_until"])
    ):
        return {"admitted": False, "reason": "target_effective_time"}
    records, _ = eligible_records(released_packet(packet), entity)
    eligible = {r["id"]: r for r in records}
    references = proposal["evidence_refs"]
    for ref in references:
        r = eligible.get(ref.get("id"))
        if (
            r is None
            or not ref.get("quote")
            or ref["quote"] not in (r.get("content") or "")
        ):
            return {"admitted": False, "reason": "ineligible_or_invalid_citation"}
        if relative_scope(r, packet) is not True:
            return {"admitted": False, "reason": "relative_date_scope"}
        if instant(proposal["effective_from"]) < instant(
            r["effective_from"]
        ) or instant(proposal["effective_until"]) > instant(r["effective_until"]):
            return {"admitted": False, "reason": "validity_scope"}
    from .reason_predicates import detected_predicates

    causes = detected_predicates({}, released_packet(packet))
    if "DISPATCHER_DATE_UNAVAILABLE" in causes:
        return {"admitted": False, "reason": "validity_scope"}
    if "DISPATCHER_VALUE_UNAVAILABLE" in causes:
        return {"admitted": False, "reason": "dispatcher_value_unavailable"}
    parsed = [
        (
            r,
            *extract_value(
                r.get("content") or "",
                packet["field"],
                packet.get("facts", {}),
                current_value=packet["current_state"][entity][packet["field"]],
                source=r,
            ),
        )
        for r in records
    ]
    # Approximate duration is evidence but not a scalar planning value.
    known_pairs = [
        (record, value)
        for record, value, status in parsed
        if value is not None and status != "approximate_duration"
    ]
    known = [value for _record, value in known_pairs]
    cited_parsed = [
        (record, value, status)
        for record, value, status in parsed
        if record["id"] in {ref.get("id") for ref in references}
    ]
    if (
        packet["field"] == "service_duration"
        and any(
            status == "approximate_duration" for _record, _value, status in cited_parsed
        )
        and not any(
            value == proposal["value"] and status != "approximate_duration"
            for _record, value, status in parsed
        )
    ):
        return {"admitted": False, "reason": "approximate_duration_not_scalar"}
    if (
        packet["field"] == "receiving_window_start"
        and any(
            status == "start_permission_not_bound"
            for _record, _value, status in cited_parsed
        )
        and not any(value is not None for _record, value, _status in parsed)
    ):
        return {"admitted": False, "reason": "permission_not_lower_bound"}
    distinct = {json.dumps(v) for v in known}
    intersected_bounds = (
        len(distinct) > 1
        and packet["field"] in {"receiving_window_start", "receiving_window_end"}
        and all(
            is_physical_bound(r.get("content") or "", packet["field"])
            for r, _v in known_pairs
        )
    )
    if len(distinct) > 1 and not intersected_bounds:
        return {"admitted": False, "reason": "structured_grammar_conflict"}
    expected = (
        (
            max(known)
            if packet["field"] == "receiving_window_start"
            else min(known)
            if packet["field"] == "receiving_window_end"
            else None
        )
        if intersected_bounds
        else None
    )
    if intersected_bounds and proposal["value"] != expected:
        return {"admitted": False, "reason": "parsed_fact_contradiction"}
    if not intersected_bounds and known and any(v != proposal["value"] for v in known):
        return {"admitted": False, "reason": "parsed_fact_contradiction"}
    return {
        "admitted": True,
        "reason": "structural_provenance_checks_only",
        "prose_entailment_verified": False,
    }


def apply_decision(
    packet: dict[str, Any], proposal: dict[str, Any], gated: bool
) -> dict[str, Any]:
    state = copy.deepcopy(packet["current_state"])
    contract = normalize_common_output(packet, proposal)
    canonical = contract["output"]
    common = contract["validation"]
    closure = contract["authority_closure"]
    rejection: dict[str, Any] | None
    if not common["valid"]:
        accepted = {
            "admitted": False,
            "reason": "output_contract_failure",
            "output_contract": common,
            "authority_closure": closure,
        }
        rejection = {
            "kind": "malformed_or_unqualified_output",
            "errors": common["errors"],
        }
    else:
        accepted = (
            admission(packet, canonical)
            if gated
            else {
                "admitted": contract["valid"],
                "reason": "common_shape_only",
            }
        )
        accepted["output_contract"] = common
        accepted["authority_closure"] = closure
        rejection = (
            {"kind": "gate_rejected_proposal", "reason": accepted["reason"]}
            if gated and not accepted["admitted"]
            else None
        )
    fallback_result = None
    final_decision: Any = copy.deepcopy(canonical)
    if gated and rejection and rejection["kind"] == "gate_rejected_proposal":
        reason_to_fallback = {
            "target_scope": ("entity_unresolved", ["entity"]),
            "target_effective_time": (
                "dispatcher_date_unavailable",
                ["effective_interval"],
            ),
            "relative_date_scope": (
                "dispatcher_date_unavailable",
                ["effective_interval"],
            ),
            "validity_scope": ("dispatcher_date_unavailable", ["effective_interval"]),
            "dispatcher_value_unavailable": (
                "missing_dispatch_value",
                ["authoritative_value"],
            ),
            "structured_grammar_conflict": (
                "conflicting_evidence",
                ["authoritative_value"],
            ),
            "parsed_fact_contradiction": (
                "conflicting_evidence",
                ["authoritative_value"],
            ),
            "approximate_duration_not_scalar": (
                "approximate_duration",
                ["authoritative_value"],
            ),
            "permission_not_lower_bound": (
                "start_permission_not_bound",
                ["authoritative_value"],
            ),
        }.get(str(accepted["reason"]))
        if str(accepted["reason"]) == "ineligible_or_invalid_citation" and isinstance(
            canonical, dict
        ):
            cited_ids = {
                ref.get("id")
                for ref in canonical.get("evidence_refs", [])
                if isinstance(ref, dict)
            }
            cited = [r for r in packet.get("evidence", []) if r.get("id") in cited_ids]
            if cited and any(r.get("verified") is not True for r in cited):
                reason_to_fallback = ("unverified_support", ["supporting_evidence"])
            elif cited and any(
                not r.get("available_at")
                or instant(r["available_at"]) > instant(packet["decision_time"])
                for r in cited
            ):
                reason_to_fallback = ("unreleased_support", ["supporting_evidence"])
            elif (
                cited
                and any(
                    r.get("revoked_at")
                    and instant(r["revoked_at"]) <= instant(packet["decision_time"])
                    for r in cited
                )
                or cited
                and any(
                    r.get("effective_until")
                    and instant(r["effective_until"])
                    <= instant(packet["effective_time"])
                    for r in cited
                )
            ):
                reason_to_fallback = ("expired_support", ["supporting_evidence"])
        if reason_to_fallback is not None:
            fallback = referral(packet, reason_to_fallback[0], reason_to_fallback[1])
            fallback_result_contract = normalize_common_output(packet, fallback)
            fallback_closure = fallback_result_contract["authority_closure"]
            fallback_contract = fallback_result_contract["validation"]
            fallback_result = {
                "candidate": fallback,
                "authority_closure": fallback_closure,
                "output_contract": fallback_contract,
                "accepted": fallback_contract["valid"],
            }
            if fallback_contract["valid"]:
                final_decision = fallback
    if (
        accepted["admitted"]
        and isinstance(canonical, dict)
        and canonical.get("action") in {"update", "retain"}
    ):
        state[canonical["entity_id"]][canonical["field"]] = canonical["value"]
    return {
        "state": state,
        "admission": accepted,
        "proposal_hash": packet_hash(proposal),
        # Rejections remain failed attempts; the evaluator receives the
        # original proposal and a separate rejection record.
        "final_decision": final_decision,
        "normalized_proposal": copy.deepcopy(canonical),
        "attempt_status": (
            "accepted"
            if accepted["admitted"]
            else "gate_rejected_with_valid_fallback"
            if fallback_result and fallback_result["accepted"]
            else "failed"
        ),
        "gate_rejection": rejection,
        "gate_fallback": fallback_result,
    }


def run_workflow(
    packet: dict[str, Any], authored_proposal: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Common preflight -> parity-preserving offline evidence workflows.

    Supplied proposals are authored integration inputs, not LLM generations.
    Never use article expected annotations as these proposal fixtures.
    """
    from .input_checks import check_packet

    check_packet(packet)
    public = released_packet(packet)
    result = {
        "packet_hash": packet_hash(public),
        "s0_state": copy.deepcopy(public["current_state"]),
        "s1": s1(public),
    }
    result["s1_applied"] = apply_decision(public, result["s1"], True)
    result["s1_output_contract"] = result["s1_applied"]["admission"]["output_contract"]
    if authored_proposal is not None:
        result["proposal_origin"] = "AUTHORED_INTEGRATION_FIXTURE"
        result["s2"] = apply_decision(public, authored_proposal, False)
        result["s3"] = apply_decision(public, authored_proposal, True)
        assert result["s2"]["proposal_hash"] == result["s3"]["proposal_hash"]
    return result
