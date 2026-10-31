"""P7 source-first components. Original P6 scores remain archived unchanged."""
from __future__ import annotations

import copy
import json
from typing import Any

from stage2.core.exact import exact_solve


def evaluate_outcome(definition: dict[str, Any], trace: bytes, decision: dict[str, Any] | None,
                     replay: dict[str, Any] | None, *, condition: dict[str, bool]) -> dict[str, Any]:
    public = definition['public']
    matching = [f for f in definition['facts'] if (f['entity'], f['field'], f['scope']) == (public['entity'], public['field'], public['scope'])]
    valid = [f for f in matching if f['verified'] and f['authority'] == 'confirmed' and f['available_at'] <= definition['epoch']
             and f['effective_from'] <= definition['effective_time'] < f['effective_to'] and f['access'] not in ('UNKNOWN', 'RESTRICTED_OR_FUTURE')]
    unresolved = any(f['authority'] == 'unknown' for f in matching) or len(valid) > 1
    events = list(map(json.loads, trace.splitlines()))
    releases = []
    attempted_channels: set[str] = set()
    questions = unnecessary = unauthorized = wording_flags = 0
    seen_answered: set[tuple[str, str, str]] = set()
    for event in events:
        responses = event['response'] if isinstance(event['response'], list) else [event['response']]
        if event['action'] == 'ASK_USER':
            for q, response in zip(event.get('arguments', []), responses):
                questions += 1
                target = (q.get('entity'), q.get('field'), q.get('scope'))
                correct_target = target == (public['entity'], public['field'], public['scope'])
                unnecessary += int(target in seen_answered or not correct_target or q.get('owner') != 'dispatcher')
                unauthorized += int(response.get('status') == 'NOT_AUTHORIZED')
                text = q.get('wording', '').lower()
                # Transparent narrow wording/slot audit, not a semantic LLM judge.
                wording_flags += int(q.get('field') == 'service_duration' and any(w in text for w in ['receiver permit', 'opening hour', 'access permission', 'effective date']))
                if correct_target and q.get('owner') == 'dispatcher':
                    attempted_channels.add('user')
                if response.get('status') == 'ANSWERED': seen_answered.add(target)
        if event['action'] == 'CALL_TOOL' and event['arguments'].get('tool') == 'lookup_snapshot':
            a = event['arguments']['arguments']
            if (a.get('entity'), a.get('field'), a.get('scope')) == (public['entity'], public['field'], public['scope']):
                attempted_channels.add('tool')
        for response in responses:
            if response.get('status') in ('ANSWERED', 'OK') and 'fact_id' in response:
                if event['action'] == 'ASK_USER' and condition['user_answers']:
                    releases.append((response, 'user'))
                if event['action'] == 'CALL_TOOL' and condition['tools'] and event['arguments'].get('tool') == 'lookup_snapshot':
                    releases.append((response, 'tool'))
    acquired = [f for f in valid if any(x['fact_id'] == f['id'] and x.get('value') == f['value'] and x.get('provenance') == f['source']
                and ((channel == 'user' and f['owner'] == 'dispatcher' and f['access'] in ('USER_KNOWN', 'BOTH_AVAILABLE'))
                     or (channel == 'tool' and f['access'] in ('TOOL_REQUIRED', 'BOTH_AVAILABLE'))) for x, channel in releases)]
    numeric = bool(decision and decision['action'] in ('UPDATE', 'RETAIN'))
    action_correct = bool(decision and type(decision['value']) is int and (decision['action'] == 'UPDATE' and decision['value'] != public['current']
                                       or decision['action'] == 'RETAIN' and decision['value'] == public['current'])) if numeric else None
    grounding = bool(numeric and not unresolved and any(f['value'] == (decision or {}).get('value') and f['id'] in (decision or {}).get('evidence', []) for f in acquired))
    oracle = None
    if len(valid) == 1:
        instance = copy.deepcopy(definition['routing']); instance['orders'][0]['service_s'] = valid[0]['value'] * 60
        oracle = exact_solve(instance)
    feasibility = replay.get('route_check', {}).get('valid') if replay and replay.get('route_check') else None
    correct_numeric = bool(numeric and grounding and action_correct and oracle and oracle['status'] == 'FEASIBLE')
    can_user = any(f['owner'] == 'dispatcher' and f['access'] in ('USER_KNOWN', 'BOTH_AVAILABLE') for f in valid) and condition['user_answers']
    can_tool = any(f['access'] in ('TOOL_REQUIRED', 'BOTH_AVAILABLE') for f in valid) and condition['tools']
    enabled = {c for c, flag in [('user', condition['user_answers']), ('tool', condition['tools'])] if flag}
    refusal_justified = bool(decision and not unresolved and decision['action'] == 'INSUFFICIENT' and not acquired and not can_user and not can_tool
                             and enabled <= attempted_channels and decision['value'] is None and decision['missing_slots'] == ['service_duration'])
    unnecessary_refusal = bool(decision and decision['action'] == 'INSUFFICIENT' and (acquired or can_user or can_tool))
    outcome = correct_numeric or refusal_justified
    return {'reference_status': 'unresolved' if unresolved else 'exploratory_source_reference', 'evidence_grounding': grounding if numeric else None,
            'action_correctness': action_correct, 'feasibility': feasibility, 'independent_outcome_correct': None if unresolved else outcome,
            'correct_grounded_numeric_decision': correct_numeric, 'correct_justified_refusal': refusal_justified,
            'unnecessary_refusal': unnecessary_refusal, 'deferred_handoff': bool(decision and decision['action'] == 'CLARIFY'),
            'useful_I2': None if unresolved else bool(outcome and replay and replay['I2']['admitted']),
            'useful_I3': None if unresolved else bool(outcome and replay and replay['I3']['admitted']),
            'unsupported_admission_I2': bool(numeric and replay and replay['I2']['admitted'] and not grounding),
            'unsupported_admission_I3': bool(numeric and replay and replay['I3']['admitted'] and not grounding),
            'unnecessary_questions': unnecessary, 'unauthorized_user_requests': unauthorized, 'wording_field_mismatch_flags': wording_flags,
            'atomic_questions_audited': questions, 'oracle_routes': oracle, 'denominator': 1}
