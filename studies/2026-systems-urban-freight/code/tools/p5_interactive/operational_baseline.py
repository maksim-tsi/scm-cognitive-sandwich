"""D-INT policy on the identical public packet and released observations only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.p5_interactive.operational import route_signature, support
from tools.p5_interactive.providers import envelope, save_json
from tools.padua_pilot.transport import _save


class OperationalBaseline:
    kind = 'deterministic_policy_not_LLM'

    def send(self, body: bytes, request_id: str, directory: Path) -> tuple[str, int]:
        request = json.loads(body); messages = request['messages']; packet = json.loads(messages[1]['content'])
        definition = {'public': packet['public'], 'epoch': packet['decision_epoch'], 'effective_time': packet['target_effective_time'], 'presentation': packet['public'].get('presentation')}
        public = packet['public']; conditions = packet['conditions']
        records = {r['id']: r for r in packet['records'] if 'value' in r or 'text' in r}
        observations = [json.loads(m['content']) for m in messages[2:] if m['role'] == 'user']
        closed: set[tuple[str,str]] = set();solution=None
        for i,m in enumerate(messages[2:],2):
            if m['role'] != 'user':continue
            env=json.loads(m['content'])['environment_result'];previous=json.loads(messages[i-1]['content'])
            responses=env if isinstance(env,list) else [env]
            for response in responses:
                for r in response.get('records',[]):records[r['id']]=r
            if previous['action']=='ASK_USER':
                for q,r in zip(previous['questions'],responses):
                    closed.add((q['field'],'user'))
            elif previous['tool']=='lookup_snapshot':closed.add((previous['arguments']['slot'],'tool'))
            elif previous['tool']=='plan_route':solution=env.get('solution')
        good=support(definition,list(records.values()));missing=[s for s,rs in good.items() if not rs]
        if public.get('source_discovery') == 'consult_released_candidate_updates':
            # A released, applicable catalog entry can supersede a currently visible
            # value. Consult it through the same counted channels as the subjects.
            for entry in packet['records']:
                slot = entry['slot']; binding = public['bindings'].get(slot)
                if (binding and entry['id'] not in records and entry['available_at'] <= definition['epoch']
                    and entry['effective_from'] <= definition['effective_time'] < entry['effective_to']
                    and entry['entity'] == public['entity'] and entry['scope'] == public['scope']
                    and entry['owner'] == binding['owner'] and entry['verified'] and entry['authority'] == 'confirmed'
                    and entry.get('issuer_role') in binding.get('permitted_issuer_roles', [entry.get('issuer_role')])):
                    paths = public['channels'][slot]
                    if any(paths[c] != 'unavailable' and (slot,c) not in closed for c in ('user','tool')) and slot not in missing:
                        missing.append(slot)
        remaining=observations[-1]['remaining'] if observations else {'questions':3,'tools':3,'model_responses':7}
        unavailable=[s for s in missing if not ((conditions['user_answers_available'] and remaining['questions'] and
                     public['channels'][s]['user']!='unavailable' and (s,'user') not in closed) or
                    (conditions['tools_available'] and remaining['tools'] and public['channels'][s]['tool']!='unavailable' and (s,'tool') not in closed))]
        event: dict[str, Any]
        if missing and unavailable:
            event={'action':'FINAL','decision':{'action':'INSUFFICIENT','parameters':{},'plan':None,'evidence':[], 'missing_slots':missing}}
        elif missing:
            ask=[s for s in missing if conditions['user_answers_available'] and public['channels'][s]['user']!='unavailable' and (s,'user') not in closed][:remaining['questions']]
            if ask:
                event={'action':'ASK_USER','questions':[{'wording':f'Confirm the authoritative {s} for this booking.', 'entity':public['entity'],'scope':public['scope'],'field':s,'owner':'dispatcher','kind':'indispensable'} for s in ask]}
            else:
                slot=next(s for s in missing if conditions['tools_available'] and public['channels'][s]['tool']!='unavailable' and (s,'tool') not in closed)
                event={'action':'CALL_TOOL','tool':'lookup_snapshot','arguments':{'slot':slot}}
        else:
            params={s:rs[0]['value'] for s,rs in good.items()};evidence=[rs[0]['id'] for rs in good.values()]
            if solution is None and conditions['tools_available'] and remaining['tools']:
                event={'action':'CALL_TOOL','tool':'plan_route','arguments':{'parameters':params}}
            else:
                if solution and solution['status']=='INFEASIBLE_CERTIFIED':action='INFEASIBLE';plan=None
                else:
                    plan=solution if solution and solution['status']=='FEASIBLE' else {'status':'FEASIBLE','routes':public['current_routes']}
                    changed=params!=public['current_parameters'] or route_signature(plan)!=public['current_routes']
                    action='UPDATE' if changed else 'RETAIN'
                event={'action':'FINAL','decision':{'action':action,'parameters':params,'plan':plan,'evidence':evidence,'missing_slots':[]}}
        _save(directory/'response.bin',envelope(event,'deepseek' if request['model']=='deepseek-flash' else 'qwen'))
        save_json(directory/'http.json',{'synthetic':True,'http_status':200});return 'complete',200
