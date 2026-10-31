"""Public, case-label-blind reason ontology and evidence predicates.

Reason aliases normalize spelling only. A reason qualifies only when its
specific public predicate is independently found in the supplied packet. This
module does not read annotations or scorer accepted codes.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from typing import Any


def _norm(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value.casefold().strip()) or None


# Predicate IDs describe actionable causes, not system implementation states.
# Aliases are generic policy vocabulary and exact legacy runtime spellings.
REASON_ALIASES: dict[str, str | tuple[str, ...]] = {
    # An entity cannot be identified from the target and packet message.
    "missing_entity": "ENTITY_UNRESOLVED",
    "ambiguous_entity": "ENTITY_UNRESOLVED",
    "unknown_entity": "ENTITY_UNRESOLVED",
    "entity_unresolved": "ENTITY_UNRESOLVED",
    # The primary duration contract requires an explicit planning allowance.
    "approximate_duration": "APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE",
    "approximate_duration_needs_planning_allowance": "APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE",
    "estimate_requires_planning_allowance": "APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE",
    # Permission does not by itself establish a lower bound.
    "start_permission_not_bound": "PERMISSION_IS_NOT_A_LOWER_BOUND",
    "permission_not_lower_bound": "PERMISSION_IS_NOT_A_LOWER_BOUND",
    "start_permission_is_not_a_lower_bound": "PERMISSION_IS_NOT_A_LOWER_BOUND",
    # Evidence eligibility/release status is a specific reason, not generic
    # parser noncoverage.
    "unreleased_support": "SUPPORT_UNRELEASED",
    "unverified_support": "SUPPORT_UNVERIFIED",
    "expired_support": "SUPPORT_EXPIRED",
    "support_unreleased_or_unverified": "SUPPORT_UNUSABLE_UNSPECIFIED",
    # Dispatcher-owned planning facts remain distinguishable from receiver
    # approval and from a generally unparsed message.
    "missing_dispatch_value": "DISPATCHER_VALUE_UNAVAILABLE",
    "missing_dispatch_date": "DISPATCHER_DATE_UNAVAILABLE",
    "missing_dispatch_value_or_date": "DISPATCHER_VALUE_OR_DATE_UNAVAILABLE",
    "dispatcher_value_unavailable": "DISPATCHER_VALUE_UNAVAILABLE",
    "dispatcher_date_unavailable": "DISPATCHER_DATE_UNAVAILABLE",
    # A source conflict is distinct from unexplained noncoverage.
    "conflicting_evidence": "ELIGIBLE_EVIDENCE_CONFLICT",
    "evidence_conflict": "ELIGIBLE_EVIDENCE_CONFLICT",
    "missing_entity_and_permission_not_lower_bound": (
        "ENTITY_UNRESOLVED",
        "PERMISSION_IS_NOT_A_LOWER_BOUND",
    ),
    # These remain broad and cannot qualify as a specific cause.
    "parser_noncoverage": "INTERPRETATION_UNSPECIFIED",
    "ambiguous_values": "INTERPRETATION_UNSPECIFIED",
    "invalid_time": "INTERPRETATION_UNSPECIFIED",
    "interpretation_needed": "INTERPRETATION_UNSPECIFIED",
    "unconfirmed_language": "CONFIRMATION_UNSPECIFIED",
    "confirmation_needed": "CONFIRMATION_UNSPECIFIED",
}

SPECIFIC_PREDICATES = {
    "ENTITY_UNRESOLVED",
    "APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE",
    "PERMISSION_IS_NOT_A_LOWER_BOUND",
    "SUPPORT_NOT_CURRENTLY_USABLE",
    "SUPPORT_UNRELEASED",
    "SUPPORT_UNVERIFIED",
    "SUPPORT_EXPIRED",
    "DISPATCHER_VALUE_UNAVAILABLE",
    "DISPATCHER_DATE_UNAVAILABLE",
    "ELIGIBLE_EVIDENCE_CONFLICT",
}
REASON_ALIASES.update(
    {predicate.casefold(): predicate for predicate in SPECIFIC_PREDICATES}
)
# Published spelling equivalents used by independent annotation interfaces.
# These map semantic vocabulary only, never a case ID, action or expected value.
# Every alias still has to satisfy the same packet-grounded predicate(s).
REASON_ALIASES.update(
    {
        "approximate_duration_requires_planning_allowance": "APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE",
        "permission_not_earliest_bound": "PERMISSION_IS_NOT_A_LOWER_BOUND",
        "ambiguous_booked_entity": "ENTITY_UNRESOLVED",
        "ambiguous_entity_and_unsupported_bound": (
            "ENTITY_UNRESOLVED",
            "PERMISSION_IS_NOT_A_LOWER_BOUND",
        ),
        "expired_receiver_instruction": "SUPPORT_EXPIRED",
        "unverified_receiver_request": "SUPPORT_UNVERIFIED",
        "unauthenticated_receiver_report": "SUPPORT_UNVERIFIED",
        "unreleased_receiver_record": "SUPPORT_UNRELEASED",
        "missing_dispatch_planning_allowance": "DISPATCHER_VALUE_UNAVAILABLE",
        "missing_dispatch_value_and_effective_date": (
            "DISPATCHER_VALUE_UNAVAILABLE",
            "DISPATCHER_DATE_UNAVAILABLE",
        ),
    }
)


def normalize_reason(reason: Any) -> str | tuple[str, ...] | None:
    """Map exact public aliases to ontology IDs; never interpret free prose."""
    text = _norm(reason)
    return REASON_ALIASES.get(text) if text is not None else None


def _message_resolves_entity(packet: Mapping[str, Any]) -> bool:
    entities = packet.get("entities")
    if not isinstance(entities, list):
        return False
    ids = {e.get("id") for e in entities if isinstance(e, Mapping)}
    target = packet.get("target_entity")
    if target:
        return target in ids
    message = _norm(packet.get("message")) or ""
    hits: set[Any] = set()
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        for alias in [entity.get("id"), entity.get("name"), *entity.get("aliases", [])]:
            normalized = _norm(alias)
            if normalized and re.search(
                r"(?<!\w)" + re.escape(normalized) + r"(?!\w)", message
            ):
                hits.add(entity.get("id"))
    return len(hits) == 1


def _eligible_public_records(packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    from .runtime import (
        eligible_records,
        relative_scope,
        released_packet,
        resolve_entity,
    )

    target = packet.get("target_entity")
    if not isinstance(target, str):
        target, _ = resolve_entity(dict(packet))
    if not target:
        return []
    try:
        public_packet = released_packet(dict(packet))
        records, _ = eligible_records(public_packet, target)
    except (KeyError, TypeError, ValueError):
        return []
    return [
        record
        for record in records
        if isinstance(record, Mapping)
        and relative_scope(dict(record), public_packet) is True
    ]


def _approximate_duration_present(packet: Mapping[str, Any]) -> bool:
    if packet.get("field") != "service_duration":
        return False
    evidence = _eligible_public_records(packet)
    approx = re.compile(
        r"\b(?:about|approximately|approx\.?|roughly|around|estimated?|estimate|circa|more\s+or\s+less)\b|~|\+\s*/\s*-",
        re.IGNORECASE,
    )
    approximate_sources = [
        record
        for record in evidence
        if isinstance(record.get("content"), str) and approx.search(record["content"])
    ]
    if not approximate_sources:
        return False
    # A separately applicable explicit planning allowance or a positive keep
    # instruction can resolve the operative decision despite an estimate.
    from .runtime import extract_value

    for record in evidence:
        content = record.get("content") or ""
        if re.search(
            r"\bkeep\s+(?:the\s+)?(?:regular|current|usual)\s+plan\b",
            content,
            re.IGNORECASE,
        ):
            return False
        value, status = extract_value(
            content, "service_duration", packet.get("facts", {}), source=dict(record)
        )
        if value is not None and status != "approximate_duration":
            return False
    return True


def _permission_is_not_bound(packet: Mapping[str, Any]) -> bool:
    if packet.get("field") != "receiving_window_start":
        return False
    evidence = _eligible_public_records(packet)
    from .runtime import extract_value, relative_scope

    # The common parser protects reporting, negation and conditional scope.
    # A lexical permission hit alone is not an operative instruction.
    statuses = [
        extract_value(
            r.get("content") or "",
            "receiving_window_start",
            packet.get("facts", {}),
            source=dict(r),
        )[1]
        for r in evidence
        if relative_scope(dict(r), dict(packet)) is True
    ]
    if "start_permission_not_bound" not in statuses:
        return False
    return not any(
        extract_value(
            r.get("content") or "",
            "receiving_window_start",
            packet.get("facts", {}),
            source=dict(r),
        )[0]
        is not None
        for r in evidence
        if relative_scope(dict(r), dict(packet)) is True
    )


def _support_status_predicates(
    packet: Mapping[str, Any], output: Mapping[str, Any]
) -> set[str]:
    from .authority_closure import _relevant_records

    records = _relevant_records(packet)
    if not isinstance(records, list):
        return set()
    decision = packet.get("decision_time")
    try:
        now = dt.datetime.fromisoformat(decision) if isinstance(decision, str) else None
    except ValueError:
        now = None
    entity = packet.get("target_entity")
    field = packet.get("field")
    selected = [
        r
        for r in records
        if isinstance(r, Mapping)
        and (not entity or entity in r.get("entity_ids", []))
        and (not field or field in r.get("fields", []))
    ]
    detected: set[str] = set()
    for record in selected:
        if record.get("source_type") not in {
            "receiver_confirmation",
            "signed_schedule",
            "dispatcher_instruction",
        }:
            detected.add("SUPPORT_NOT_CURRENTLY_USABLE")
        if record.get("verified") is not True:
            detected.add("SUPPORT_UNVERIFIED")
        available = record.get("available_at")
        try:
            available_at = (
                dt.datetime.fromisoformat(available)
                if isinstance(available, str)
                else None
            )
        except ValueError:
            available_at = None
        if available_at is None or (now is not None and available_at > now):
            detected.add("SUPPORT_UNRELEASED")
        revoked = record.get("revoked_at")
        try:
            revoked_at = (
                dt.datetime.fromisoformat(revoked) if isinstance(revoked, str) else None
            )
        except ValueError:
            revoked_at = None
        if revoked_at is not None and (now is None or revoked_at <= now):
            detected.add("SUPPORT_NOT_CURRENTLY_USABLE")
        for key in ("effective_from", "effective_until"):
            bound = record.get(key)
            try:
                bound_at = (
                    dt.datetime.fromisoformat(bound) if isinstance(bound, str) else None
                )
            except ValueError:
                bound_at = None
            target = packet.get("effective_time")
            try:
                effective = (
                    dt.datetime.fromisoformat(target)
                    if isinstance(target, str)
                    else None
                )
            except ValueError:
                effective = None
            if bound_at is None or effective is None:
                detected.add("SUPPORT_NOT_CURRENTLY_USABLE")
            if (
                bound_at is not None
                and effective is not None
                and key == "effective_from"
                and bound_at > effective
            ):
                detected.add("SUPPORT_NOT_CURRENTLY_USABLE")
            if (
                bound_at is not None
                and effective is not None
                and key == "effective_until"
                and bound_at <= effective
            ):
                detected.add("SUPPORT_EXPIRED")
    if not selected:
        return set()
    # A usable, applicable value means an unrelated bad record cannot explain
    # an evidence-unavailability referral.
    from .runtime import extract_value

    usable = _eligible_public_records(packet)
    if any(
        extract_value(
            r.get("content") or "",
            str(packet.get("field", "")),
            packet.get("facts", {}),
            source=dict(r),
        )[0]
        is not None
        for r in usable
    ):
        return set()
    return detected


def _released_dispatchers(packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Inspect released owned content independently of interval admission."""
    from .runtime import instant, released_packet, resolve_entity

    entity, _ = resolve_entity(dict(packet))
    if not entity:
        return []
    public = released_packet(dict(packet))
    records = []
    for r in public.get("evidence", []):
        if (
            r.get("source_type") != "dispatcher_instruction"
            or r.get("verified") is not True
            or entity not in r.get("entity_ids", [])
            or packet.get("field") not in r.get("fields", [])
            or not isinstance(r.get("content"), str)
        ):
            continue
        if r.get("revoked_at") and instant(r["revoked_at"]) <= instant(
            packet["decision_time"]
        ):
            continue
        records.append(r)
    # Only an actually eligible successor can supersede a prior instruction.
    eligible_ids = {r.get("id") for r in _eligible_public_records(packet)}
    superseded = {
        old
        for r in records
        if r.get("id") in eligible_ids
        for old in r.get("supersedes", [])
    }
    return [r for r in records if r.get("id") not in superseded]


def _explicit_dispatch_absence(
    record: Mapping[str, Any], packet: Mapping[str, Any]
) -> tuple[bool, bool]:
    """Bounded positive absence evidence, independent of scalar noncoverage."""
    text = record.get("content") or ""
    value_slot = r"(?:(?:the|a|an|its)\s+)?(?:(?:replacement|revised)\s+)?(?:planning\s+)?(?:service\s+)?(?:time\s+)?(?:allowance|value|duration)"
    date_slot = r"(?:(?:the|a|an|its)\s+)?(?:instruction\s+)?(?:activation|effective|start)\s+date"
    supplied = r"(?:provided|supplied|specified|confirmed|determined)"
    coordinated = (
        r"neither\s+(?:"
        + value_slot
        + r"\s+nor\s+"
        + date_slot
        + r"|"
        + date_slot
        + r"\s+nor\s+"
        + value_slot
        + r")\s+(?:(?:was|were)\s+|(?:has|have)\s+been\s+)"
        + supplied
    )
    absence = (
        r"(?:(?:(?:is|was|were)\s+not\s+(?:yet\s+)?|(?:has|have)\s+not\s+(?:yet\s+)?been\s+)"
        + supplied
        + r"|(?:is\s+)?to be "
        + supplied
        + r"|(?:(?:is|was)\s+)?(?:pending|missing|unavailable))"
    )
    missing_value = value_slot + r"\s+" + absence
    missing_date = date_slot + r"\s+" + absence
    request = r"(?:please\s+)?(?:supply|provide|confirm|specify)\s+" + value_slot
    value_absent = date_absent = False
    # Clausal absence is independent of scalar parsing. Preserve statement
    # polarity and do not split away reporting or conditional operators.
    if re.search(
        r"\b(?:said|says?|heard|told|reportedly|reports?|mentions?|claims?|suggested|unconfirmed|tentative|draft|rumou?r|perhaps|possibly|uncertain|maybe|might|if|unless|provided that|only when)\b|\bnot (?:true|correct)\b|(?:^|[;.,])\s*not (?:approved|confirmed)\s*[:;,.]|\bproposed but\b",
        text,
        re.IGNORECASE,
    ):
        return False, False
    # A prohibition against inventing an absent fact does not negate the
    # preceding absence assertion. No other arbitrary suffix is removed.
    text = re.sub(
        r"[,;.]?\s*(?:please\s+)?do not invent either[.!]?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    for clause in re.split(r"[;.,:]|\bbut\b", text, flags=re.IGNORECASE):
        clause = clause.strip()
        if re.fullmatch(coordinated, clause, re.IGNORECASE):
            value_absent = date_absent = True
        elif re.fullmatch(missing_value + r"|" + request, clause, re.IGNORECASE):
            value_absent = True
        elif re.fullmatch(missing_date, clause, re.IGNORECASE):
            date_absent = True
    return value_absent, date_absent


def _dispatch_value_unavailable(packet: Mapping[str, Any]) -> bool:
    from .runtime import extract_value

    field = str(packet.get("field", ""))

    def scalar(record: Mapping[str, Any]) -> bool:
        value, status = extract_value(
            record.get("content") or "",
            field,
            packet.get("facts", {}),
            source=dict(record),
        )
        return value is not None and status != "approximate_duration"

    eligible = _eligible_public_records(packet)
    if any(scalar(r) for r in eligible):
        return False
    dispatchers = _released_dispatchers(packet)
    if dispatchers:
        if any(scalar(r) for r in dispatchers):
            return False
        # Explicit absent/pending owned planning content is evidence of an
        # absent value; an eligible but unparsed instruction is not.
        return any(_explicit_dispatch_absence(r, packet)[0] for r in dispatchers)
    # A direct scalar-free change request for a booked stop establishes one
    # narrowly answerable planning question only when the requested field has
    # no relevant source. Opaque, unreleased and ineligible sources remain
    # relevant evidence states; parser noncoverage never proves absence.
    if field != "service_duration" or not _message_resolves_entity(packet):
        return False
    candidates = plausible_entities(packet)
    # Explicit field/entity metadata is enough to establish source presence.
    # Unknown prose must not disappear through a finite vocabulary filter.
    if any(
        field in r.get("fields", [])
        and set(candidates).intersection(r.get("entity_ids", []))
        for r in packet.get("evidence", [])
        if isinstance(r, Mapping)
    ):
        return False
    aliases = [
        alias
        for entity in packet.get("entities", [])
        if entity.get("id") in candidates
        for alias in [entity.get("id"), entity.get("name"), *entity.get("aliases", [])]
        if isinstance(alias, str) and alias.strip()
    ]
    target = "(?:" + "|".join(re.escape(_norm(alias) or "") for alias in aliases) + ")"
    scope = r"(?:\s+(?:for|at|to)\s+" + target + r")?"
    duration = (
        r"(?:service\s+(?:duration|time)|planning\s+(?:service\s+)?allowance"
        r"|time\s+on\s+site|unloading\s+time)"
    )
    request = (
        r"(?:(?:please\s+)|(?:(?:the\s+)?(?:receiver|recipient|shop)\s+"
        r"(?:asks?(?:\s+us)?\s+to|requests?(?:\s+us)?\s+to|requests?\s+that\s+we)\s+))?(?:"
        r"(?:revise|change|adjust|update|increase|decrease|shorten|lengthen|extend|reduce)\s+"
        r"(?:the\s+)?"
        + duration
        + scope
        + r"|make\s+(?:the\s+)?(?:booked\s+)?(?:stop|visit)"
        + scope
        + r"\s+(?:shorter|quicker|longer))"
        # An order number or calendar date is not a proposed duration scalar.
        + r"(?:\s+for\s+order\s+\d+|\s+on\s+\d{4}-\d{2}-\d{2})?[.!]?"
    )
    clauses = [
        c.strip()
        for c in re.split(r"[.;,]", _norm(packet.get("message")) or "")
        if c.strip()
    ]
    if not clauses or re.fullmatch(request, clauses[0]) is None:
        return False
    # Allow bounded explanatory absence and other-field context after the
    # operative request. Extra prose is never discarded as an arbitrary suffix.
    amount = (
        r"(?:(?:replacement|revised|new|stated)\s+)?"
        r"(?:duration|service\s+(?:duration|time)|allowance|planning\s+allowance"
        r"|value|amount|figure|number(?:\s+of\s+minutes)?|unloading\s+(?:duration|time|value|minutes))"
    )
    no_amount = (
        r"(?:without\s+(?:(?:a|any)\s+|specifying\s+)?"
        + amount
        + r"|(?:but\s+)?(?:supplies|gives|contains)\s+no\s+"
        + amount
        + r"|with\s+no\s+"
        + amount
        + r"(?:\s+specified)?)"
    )
    explanation = (
        r"no\s+"
        + amount
        + r"\s+(?:was|is|has\s+been)\s+(?:supplied|specified|provided|given)"
        + r"|"
        + no_amount
        + r"|it\s+(?:supplies|gives|contains)\s+no\s+"
        + amount
    )
    document = r"(?:(?:the|its)\s+)?(?:(?:attached|signed)\s+)?(?:sheet|schedule|document|note|page)\s+"
    # Document silence must name the operative field, rather than a bare
    # quantity noun whose referent could be unrelated. Compose it with the
    # other-field context without admitting arbitrary trailing prose.
    silence = (
        r"(?:says|contains|provides)\s+nothing\s+about\s+(?:the\s+)?"
        r"(?:(?:requested|new|revised)\s+)?(?:"
        + duration
        + r"|service\s+allowance)"
    )
    context = (
        document + r"(?:"
        r"(?:only\s+)?(?:lists?|concerns?|describes?|contains?|covers?|sets?\s+out)\s+(?:only\s+)?"
        r"(?:public\s+)?(?:opening|receiving|storefront)\s+(?:hours|windows?)"
        + r"(?:\s+(?:(?:and|but)\s+)?"
        + r"(?:"
        + no_amount
        + r"|"
        + silence
        + r"))?"
        + r"|"
        + silence
        + r")"
    )
    return all(re.fullmatch(explanation + r"|" + context, c) for c in clauses[1:])


def _dispatch_date_unavailable(packet: Mapping[str, Any]) -> bool:
    from .runtime import extract_value

    dispatchers = _released_dispatchers(packet)
    explicitly_undated = {
        r.get("id") for r in dispatchers if _explicit_dispatch_absence(r, packet)[1]
    }
    eligible = _eligible_public_records(packet)
    if explicitly_undated:
        # A value in the same incomplete instruction cannot supply its date.
        # Independent operative support can make a side instruction irrelevant.
        independent = any(
            r.get("id") not in explicitly_undated
            and (
                parsed := extract_value(
                    r.get("content") or "",
                    str(packet.get("field", "")),
                    packet.get("facts", {}),
                    source=dict(r),
                )
            )[0]
            is not None
            and parsed[1] != "approximate_duration"
            for r in eligible
        )
        return not independent
    if any(
        extract_value(
            r.get("content") or "",
            str(packet.get("field", "")),
            packet.get("facts", {}),
            source=dict(r),
        )[0]
        is not None
        and extract_value(
            r.get("content") or "",
            str(packet.get("field", "")),
            packet.get("facts", {}),
            source=dict(r),
        )[1]
        != "approximate_duration"
        for r in _eligible_public_records(packet)
    ):
        return False
    return any(
        (
            not r.get("effective_from")
            or not r.get("effective_until")
            or _explicit_dispatch_absence(r, packet)[1]
        )
        for r in dispatchers
    )


def _eligible_conflict(packet: Mapping[str, Any]) -> bool:
    from .runtime import eligible_records, extract_value, resolve_entity

    entity, _ = resolve_entity(dict(packet))
    if not entity:
        return False
    try:
        records, _ = eligible_records(dict(packet), entity)
    except (KeyError, TypeError, ValueError):
        return False
    valued = [
        (
            extract_value(
                r.get("content") or "",
                str(packet.get("field", "")),
                packet.get("facts", {}),
                source=dict(r),
            )[0],
            r,
        )
        for r in records
    ]
    valued = [
        (value, record)
        for value, record in valued
        if value is not None
        and extract_value(
            record.get("content") or "",
            str(packet.get("field", "")),
            packet.get("facts", {}),
            source=dict(record),
        )[1]
        != "approximate_duration"
    ]
    if len({repr(value) for value, _ in valued}) <= 1:
        return False
    from .runtime import is_physical_bound

    # Same-direction physical constraints intersect. Different scalar values
    # alone do not establish a contradiction.
    return not all(
        is_physical_bound(record.get("content") or "", str(packet.get("field", "")))
        for _v, record in valued
    )


def plausible_entities(packet: Mapping[str, Any]) -> list[str]:
    """Public manifest candidates selected with the same whole-alias grammar."""
    target = packet.get("target_entity")
    entities = [e for e in packet.get("entities", []) if isinstance(e, Mapping)]
    if target:
        return [target] if any(e.get("id") == target for e in entities) else []
    message = _norm(packet.get("message")) or ""
    return [
        e["id"]
        for e in entities
        if any(
            (alias_text := _norm(alias))
            and re.search(r"(?<!\w)" + re.escape(alias_text) + r"(?!\w)", message)
            for alias in [e.get("id"), e.get("name"), *e.get("aliases", [])]
        )
    ]


def detected_predicates(output: Any, packet: Any) -> set[str]:
    """Return only specific causes positively supported by public packet data."""
    if not isinstance(output, Mapping) or not isinstance(packet, Mapping):
        return set()
    candidates = plausible_entities(packet)
    if not packet.get("target_entity") and len(candidates) > 1:
        worlds = []
        for entity in candidates:
            world = dict(packet, target_entity=entity)
            # Actor-selected entity/refs cannot suppress candidate-world facts.
            candidate_output = dict(output)
            candidate_output.pop("entity_id", None)
            candidate_output.pop("evidence_refs", None)
            worlds.append(detected_predicates(candidate_output, world))
        return {"ENTITY_UNRESOLVED"} | set.intersection(*worlds)
    found: set[str] = set()
    if not _message_resolves_entity(packet):
        found.add("ENTITY_UNRESOLVED")
    if _approximate_duration_present(packet):
        found.add("APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE")
    if _permission_is_not_bound(packet):
        found.add("PERMISSION_IS_NOT_A_LOWER_BOUND")
    found.update(_support_status_predicates(packet, output))
    if _dispatch_value_unavailable(packet):
        found.add("DISPATCHER_VALUE_UNAVAILABLE")
    if _dispatch_date_unavailable(packet):
        found.add("DISPATCHER_DATE_UNAVAILABLE")
    if _eligible_conflict(packet):
        found.add("ELIGIBLE_EVIDENCE_CONFLICT")
    return found


def qualify_reason(output: Any, packet: Any) -> dict[str, Any]:
    """Check specific cause agreement; aliases alone never qualify a reason."""
    if not isinstance(output, Mapping):
        return {
            "valid": False,
            "predicate": None,
            "detected_predicates": [],
            "errors": ["output_must_be_object"],
        }
    raw = output.get("reason_code", output.get("reason"))
    normalized = normalize_reason(raw)
    predicates = (normalized,) if isinstance(normalized, str) else normalized
    detected = detected_predicates(output, packet)
    acceptable_slots = {
        "ENTITY_UNRESOLVED": {"entity"},
        "APPROXIMATE_DURATION_NEEDS_PLANNING_ALLOWANCE": {"authoritative_value"},
        "PERMISSION_IS_NOT_A_LOWER_BOUND": {"authoritative_value", "interpretation"},
        "SUPPORT_NOT_CURRENTLY_USABLE": {"supporting_evidence", "confirmation"},
        "SUPPORT_UNRELEASED": {"supporting_evidence", "confirmation"},
        "SUPPORT_UNVERIFIED": {"supporting_evidence", "confirmation"},
        "SUPPORT_EXPIRED": {"supporting_evidence", "confirmation"},
        "DISPATCHER_VALUE_UNAVAILABLE": {"authoritative_value"},
        "DISPATCHER_DATE_UNAVAILABLE": {"effective_interval"},
        "ELIGIBLE_EVIDENCE_CONFLICT": {"authoritative_value"},
    }
    required_slots = set().union(
        *(acceptable_slots.get(predicate, set()) for predicate in predicates or ())
    )
    from .output_contract import normalize_output

    slots = set(normalize_output(output)["missing_slots"])
    if predicates is None:
        errors = ["reason_not_in_public_ontology"]
    elif not predicates or any(p not in SPECIFIC_PREDICATES for p in predicates):
        errors = ["reason_too_broad_for_semantic_qualification"]
    elif not set(predicates) <= detected:
        errors = ["reason_cause_not_supported_by_public_packet"]
    elif any(not (acceptable_slots.get(p, set()) & slots) for p in predicates):
        errors = ["reason_missing_slot_mismatch"]
    else:
        errors = []
    return {
        "valid": not errors,
        "predicate": predicates[0]
        if predicates and len(predicates) == 1
        else list(predicates or ()),
        "required_slots": sorted(required_slots),
        "detected_predicates": sorted(detected),
        "errors": errors,
    }
