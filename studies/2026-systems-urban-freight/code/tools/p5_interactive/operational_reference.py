"""Independent source-first P8 references and outcome checks; never agent-visible.

Uses exhaustive initial-depot enumeration, not the subject's chosen solver or gate.
Shares declarative bindings and the existing independent route checker, not policy helpers.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from stage2.core.evaluator import evaluate as check_route
from stage2.core.exact import exact_solve

from tools.p5_interactive.source_text import wire_record


def active_sources(d: dict[str, Any], slot: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    binding = d['public']['bindings'][slot]
    valid = [r for r in records if r['slot'] == slot and r['owner'] == binding['owner'] and r['verified'] is True
             and (not binding.get('required_assertion_kind') or r.get('assertion_kind') == binding['required_assertion_kind'])
             and (not binding.get('permitted_issuer_roles') or r.get('issuer_role') in binding['permitted_issuer_roles'])
             and r['authority'] == 'confirmed' and r['precision'] == 'confirmed' and type(r['value']) is int
             and r['entity'] == d['public']['entity'] and r['scope'] == d['public']['scope']
             and r['available_at'] <= d['epoch'] and r['effective_from'] <= d['effective_time'] < r['effective_to']]
    return [r for r in valid if not any(r['id'] in new['supersedes'] and r['id'] != new['id']
            and r['available_at'] <= new['available_at'] for new in valid)]


def source_resolution(d: dict[str, Any], records: list[dict[str, Any]]) -> tuple[dict[str, int], list[str], dict[str, list[str]]]:
    params: dict[str, int] = {}; missing = []; sources = {}
    for slot in d['public']['required_slots']:
        active = active_sources(d, slot, records)
        values = {r['value'] for r in active}
        if len(values) == 1:
            params[slot] = values.pop()
            sources[slot] = sorted(r['id'] for r in active)
        else:
            missing.append(slot)
            sources[slot] = []
    return params, missing, sources


def source_values(d: dict[str, Any], records: list[dict[str, Any]]) -> tuple[dict[str, int], list[str]]:
    params, missing, _ = source_resolution(d, records)
    return params, missing


def reference_instance(d: dict[str, Any], params: dict[str, int]) -> dict[str, Any]:
    result = copy.deepcopy(d['routing'])
    for slot in d['public']['required_slots']:
        path = d['public']['bindings'][slot]['path']; target = result
        for part in path[:-1]: target = target[part]
        target[path[-1]] = params[slot]
    return result


def derive_reference(d: dict[str, Any], *, tools: bool = True, user_answers: bool = True) -> dict[str, Any]:
    accessible = [r for r in d['records'] if r['available_at'] <= d['epoch'] and
                  (r['channel'] == 'public' or r['channel'] == 'user' and user_answers and r['owner'] == 'dispatcher'
                   and d['public']['channels'][r['slot']]['user'] != 'unavailable'
                   or r['channel'] == 'tool' and tools and d['public']['channels'][r['slot']]['tool'] != 'unavailable')]
    params, missing, supporting = source_resolution(d, accessible)
    base = {'world': d['id'], 'condition': {'tools': tools, 'user_answers': user_answers},
            'parameters': params, 'missing_slots': missing, 'reference_kind': 'corrected_source_first_reference_not_external_domain_validated',
            'source_ids': sorted({rid for ids in supporting.values() for rid in ids}),
            'inspected_source_ids': sorted(r['id'] for r in accessible), 'derivation': 'independent source eligibility/supersession then exhaustive route enumeration'}
    if missing:
        branches = []
        if len(missing) == 1:
            slot = missing[0]; active = active_sources(d, slot, accessible)
            for value in sorted({r['value'] for r in active}):
                candidate = {**params, slot: value}; oracle = exact_solve(reference_instance(d, candidate))
                branches.append({'parameters': candidate, 'hypothesis_source_ids': sorted(r['id'] for r in active if r['value'] == value),
                                 'outcome': 'FEASIBLE_PLAN' if oracle['status'] == 'FEASIBLE' else 'INFEASIBLE', 'oracle': oracle})
        return {**base, 'outcome': 'INSUFFICIENT', 'oracle': None, 'conflict_branches': branches}
    x = reference_instance(d, params); oracle = exact_solve(x)
    if oracle['status'] == 'FEASIBLE':
        assert check_route(x, oracle)['valid']
        return {**base, 'outcome': 'FEASIBLE_PLAN', 'oracle': oracle}
    # An exhaustive finite enumeration with no witness is a proof on this bounded instance.
    return {**base, 'outcome': 'INFEASIBLE', 'oracle': oracle}


def evaluate_outcome(d: dict[str, Any], trace: bytes, decision: dict[str, Any] | None,
                     replay: dict[str, Any] | None, *, condition: dict[str, bool]) -> dict[str, Any]:
    ref = derive_reference(d, tools=condition['tools'], user_answers=condition['user_answers'])
    events = [json.loads(line) for line in trace.splitlines()]
    observed = {r['id']: r for r in d['records'] if r['channel'] == 'public' and r['available_at'] <= d['epoch']}
    catalog = {r['id']: r for r in d['records']}
    invalid_release = False
    optional_questions = unnecessary = denied = 0
    seen_slots: set[str] = set()
    for event in events:
        if event['action'] == 'ASK_USER':
            for q, response in zip(event['arguments'], event['response']):
                slot = q['field']; optional_questions += int(slot not in d['public']['required_slots'])
                unnecessary += int(slot in seen_slots or slot not in d['public']['required_slots'])
                denied += int(response['status'] in ('NOT_AUTHORIZED','PUBLIC_CHANNEL_UNAVAILABLE'))
                if response['status'] == 'RECORDS_RELEASED': seen_slots.add(slot)
        responses = event['response'] if isinstance(event['response'], list) else [event['response']]
        for response in responses:
            for r in response.get('records', []):
                original = catalog.get(r.get('id'))
                if original is None or wire_record(d, original) != r:
                    invalid_release = True
                else:
                    observed[r['id']] = original
    observed_params, observed_missing, observed_support = source_resolution(d, list(observed.values()))
    grounding = action_correct = feasibility = None; correct_numeric = correct_refusal = correct_infeasible = deferred = False
    if decision:
        action = decision['action']; params = decision['parameters']; plan = decision['plan']
        if action in ('UPDATE','RETAIN','INFEASIBLE'):
            grounding = set(params) == set(d['public']['required_slots']) and not observed_missing and params == observed_params
            # Select citations against ALL visible active sources, so omitting a
            # superseding record cannot resurrect an obsolete citation.
            grounding = grounding and all(set(ids).intersection(decision['evidence']) for ids in observed_support.values())
            if action in ('UPDATE','RETAIN') and plan:
                changed = params != d['public']['current_parameters'] or sorted(
                    [{'vehicle': r['vehicle'],'nodes':r['nodes']} for r in plan.get('routes',[])], key=lambda r:r['vehicle']) != d['public']['current_routes']
                action_correct = (action == 'UPDATE') == changed
                if set(params) == set(d['public']['required_slots']):
                    try: feasibility = check_route(reference_instance(d,params),plan)['valid']
                    except (ValueError,TypeError,KeyError,IndexError): feasibility = False
                correct_numeric = bool(grounding and action_correct and feasibility and ref['outcome']=='FEASIBLE_PLAN'
                                       and params == ref['parameters'] and not decision['missing_slots'])
            if action == 'INFEASIBLE':
                correct_infeasible = bool(grounding and params == ref['parameters'] and ref['outcome']=='INFEASIBLE'
                                          and plan is None and not decision['missing_slots'])
        else:
            closed: set[tuple[str,str]] = set()
            for event in events:
                if event['action']=='ASK_USER':
                    for q,response in zip(event['arguments'],event['response']):
                        if (q['entity'],q['scope'],q['owner']) == (d['public']['entity'],d['public']['scope'],'dispatcher') and response['status'] in ('PUBLIC_CHANNEL_UNAVAILABLE','NO_AUTHORITATIVE_ANSWER','RECORDS_RELEASED'):
                            closed.add((q['field'],'user'))
                elif (event['action']=='CALL_TOOL' and event['arguments']['tool']=='lookup_snapshot'
                      and event['response']['status'] in ('PUBLIC_CHANNEL_UNAVAILABLE','NO_AUTHORITATIVE_ANSWER','RECORDS_RELEASED')):
                    closed.add((event['arguments']['arguments'].get('slot'),'tool'))
            qs = max((e['questions_used'] for e in events),default=0);ts=max((e['tools_used'] for e in events),default=0)
            resource_options={(0,0)}
            for s in observed_missing:
                options=[];paths=d['public']['channels'][s]
                if condition['user_answers'] and paths['user']!='unavailable' and (s,'user') not in closed:options.append((1,0))
                if condition['tools'] and paths['tool']!='unavailable' and (s,'tool') not in closed:options.append((0,1))
                resource_options={(a+x,b+y) for a,b in resource_options for x,y in options if a+x<=3-qs and b+y<=3-ts}
            proper_tuple=bool(observed_missing and sorted(decision['missing_slots'])==sorted(observed_missing) and not params and plan is None)
            correct_refusal=bool(action=='INSUFFICIENT' and proper_tuple and not resource_options and ref['outcome']=='INSUFFICIENT')
            deferred=bool(action=='CLARIFY' and proper_tuple and resource_options)
    correct=(correct_numeric or correct_refusal or correct_infeasible) and not invalid_release
    oracle=ref['oracle'];distance=None
    if decision and decision['plan'] and feasibility:
        distance=check_route(reference_instance(d,decision['parameters']),decision['plan'])['distance_m']
    return {'denominator':1,'invalid_release_provenance':invalid_release,'reference_outcome':ref['outcome'],'evidence_grounding':grounding,'action_correctness':action_correct,
            'feasibility':feasibility,'correct_numeric_plan':correct_numeric,'correct_proven_infeasibility':correct_infeasible,
            'correct_justified_refusal':correct_refusal,'deferred_clarify':deferred,
            'unnecessary_refusal':bool(decision and decision['action']=='INSUFFICIENT' and ref['outcome']=='FEASIBLE_PLAN'),
            'independent_outcome_correct':correct,'optional_questions':optional_questions,'unnecessary_questions':unnecessary,
            'unauthorized_questions':denied,'distance_m':distance,
            'distance_regret_m':distance-oracle['distance_m'] if distance is not None and oracle and oracle['distance_m'] is not None else None,
            'useful_I2':bool(correct and replay and replay['I2']['admitted']),
            'useful_I3':bool(correct and replay and replay['I3']['admitted'])}
