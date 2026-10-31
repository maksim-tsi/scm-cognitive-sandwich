"""Offline P8 candidate validation using D-INT and the existing captured runner.

No HTTP client, credential lookup, or subject-model generation is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import permutations, product
from pathlib import Path
from typing import Any

from stage2.core.evaluator import evaluate as check_route

from tools.p5_interactive.experiment import run_episode
from tools.p5_interactive.operational import OperationalWorld, terminal_replay
from tools.p5_interactive.operational_baseline import OperationalBaseline
from tools.p5_interactive.operational_reference import (
    derive_reference,
    reference_instance,
)
from tools.p5_interactive.providers import Journal, save_json

ROOT = Path(__file__).resolve().parents[2].parent / "data"


def enumerate_routes(instance: dict[str, Any]) -> dict[str, Any]:
    """Enumerate assignments/orderings via checker; independent of OR-Tools/search status."""
    nodes=list(range(1,len(instance['distance_m'])));n=len(instance['vehicle_capacities_kg'])
    counts=0;costs=set();examples: list[dict[str, Any]]=[];tested=0
    for assignment in product(range(n),repeat=len(nodes)):
        groups=[[node for node,vehicle in zip(nodes,assignment) if vehicle==v] for v in range(n)]
        for seqs in product(*(list(permutations(g)) for g in groups)):
            plan={'status':'FEASIBLE','routes':[{'vehicle':v,'nodes':[0,*seq,0]} for v,seq in enumerate(seqs) if seq]}
            tested+=1;check=check_route(instance,plan)
            if check['valid']:
                counts+=1;costs.add(check['distance_m'])
                if len(examples)<2:examples.append(plan)
    return {'assignments_and_orders_tested':tested,'feasible_plans':counts,'distinct_distance_values_m':sorted(costs), 'examples':examples}


def replay_trace(d: dict[str, Any], trace: bytes, *, tools: bool=True, user_answers: bool=True) -> dict[str, Any]:
    world=OperationalWorld(d,tools=tools,user_answers=user_answers);decision=None
    for event in map(json.loads,trace.splitlines()):
        if event['action']=='ASK_USER':world.ask_user(event['arguments'])
        elif event['action']=='CALL_TOOL':world.call_tool(event['arguments']['tool'],event['arguments']['arguments'])
        elif event['action']=='FINAL':decision=event['arguments'];world.submit_final(decision)
        else:raise ValueError('Unknown recorded action')
    assert world.export_trace()==trace,'Deterministic transcript mismatch'
    assert decision is not None
    return terminal_replay(d,world,decision)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    scenarios=json.loads((ROOT/'research/p8/scenarios.json').read_text());refs=json.loads((ROOT/'research/p8/references.json').read_text())
    assert [derive_reference(w) for w in scenarios]==refs,'Candidate references changed'
    results=[];enumerations={}
    for w,ref in zip(scenarios,refs):
        r=run_episode(w,OperationalBaseline(),Journal(args.output/w['id'],10,0),'qwen',name='dint')
        trace=(args.output/w['id']/'dint/trace.jsonl').read_bytes()
        assert replay_trace(w,trace)==r['replay']
        assert r['actual_model_generation_attempts']==0 and r['evaluation']['useful_I3']
        results.append(r)
        if ref['oracle']:
            x=reference_instance(w,ref['parameters']);enum=enumerate_routes(x);enumerations[w['id']]=enum
            assert (enum['feasible_plans']>0)==(ref['outcome']=='FEASIBLE_PLAN')
            if enum['feasible_plans']:assert min(enum['distinct_distance_values_m'])==ref['oracle']['distance_m']
    save_json(args.output/'summary.json',{'baseline':'84e7ba0f9957410891604dcfcf3dcf650b859634','scenarios':len(scenarios),
        'real_model_generations':0,'all_D_INT_correct':True,'all_identical_transcript_replays':True,'results':results,'independent_enumeration':enumerations,
        'source_sha256':hashlib.sha256((ROOT/'research/p8/scenarios.json').read_bytes()).hexdigest()})
    print(json.dumps({'scenarios':len(scenarios),'real_model_generations':0,'D_INT_useful':sum(r['evaluation']['useful_I3'] for r in results),'enumerated':len(enumerations)}))


if __name__=='__main__':main()
