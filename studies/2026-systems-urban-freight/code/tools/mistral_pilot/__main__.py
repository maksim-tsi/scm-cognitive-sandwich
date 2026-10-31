"""One smoke plus13 exploratory Mistral episodes,91 total attempts including smoke."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from tools.p5_interactive.experiment import run_episode
from tools.p5_interactive.providers import (
    HttpClient,
    IntegrityError,
    Journal,
    capture,
    save_json,
)

ROOT = Path(__file__).resolve().parents[2].parent / "data"
PRIVATE=Path('<LOCAL_PATH_REMOVED>')


def classify(c: dict[str,Any],raw: bytes) -> str:
    code=c.get('http_status')
    if code==401:return 'invalid_api_key'
    if code==403:return 'model_permission_denied'
    if code==402:return 'insufficient_quota_or_credit'
    if code==429:return 'insufficient_quota_or_credit' if any(x in raw.lower() for x in [b'quota',b'credit',b'billing']) else 'rate_limited'
    if c.get('unknown_completion'):return 'unknown_completion'
    if code is None:return 'network_or_tls_error'
    return 'api_compatibility_or_output_failure'


def check_topup_continuation(j: Journal, expected_smokes: int = 1) -> None:
    """One owner-authorised continuation of the retained, fully processed429 smoke."""
    with j.connect() as db:
        rows=db.execute('SELECT id,episode,route,status FROM calls').fetchall()
        stop=db.execute('SELECT stop FROM settings WHERE id=1').fetchone()[0]
    expected={('SMOKE','mistral','processed')}
    if expected_smokes>=2:expected.add(('SMOKE_AFTER_OWNER_TOPUP','mistral','processed'))
    if expected_smokes==3:expected.add(('SMOKE_AFTER_OWNER_KEY_UPDATE','mistral','processed'))
    if expected_smokes not in (1,2,3) or stop or len(rows)!=expected_smokes or {r[1:] for r in rows}!=expected:
        raise IntegrityError('Continuation requires exactly the authorised processed smoke failures, no STOP')
    for row in rows:
        c=json.loads((j.root/row[0]/'capture.json').read_text())
        if c.get('http_status')!=429 or c.get('unknown_completion'):
            raise IntegrityError('Only known429 resource failures may continue after owner resource restoration')


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',action='store_true');p.add_argument('--after-owner-topup',action='store_true');p.add_argument('--after-owner-key-update',action='store_true');p.add_argument('--payg-smoke-only',action='store_true');args=p.parse_args()
    if not args.live:p.error('Explicit --live required for this single authorised pilot')
    if sum([args.after_owner_topup,args.after_owner_key_update,args.payg_smoke_only])>1:p.error('Choose one explicit continuation')
    continuing=args.after_owner_topup or args.after_owner_key_update or args.payg_smoke_only
    freeze_name='payg-pre-inference-freeze.json' if args.payg_smoke_only else 'key-update-pre-inference-freeze.json' if args.after_owner_key_update else 'topup-pre-inference-freeze.json' if args.after_owner_topup else 'pre-inference-freeze.json'
    freeze=json.loads((ROOT/'evidence/mistral-pilot'/freeze_name).read_text())
    for file,h in freeze['files'].items():
        if hashlib.sha256((ROOT/file).read_bytes()).hexdigest()!=h:raise IntegrityError('Frozen study source differs')
    pre=json.loads((PRIVATE/('preflight-key-update' if args.after_owner_key_update else 'preflight')/'receipt.json').read_text())
    if pre['status']!='authorised_model_available':raise IntegrityError('GET preflight failed; no inference')
    output=PRIVATE/'run'
    if continuing:
        if not (output/'calls.sqlite').is_file() or (PRIVATE/'results.json').exists():raise IntegrityError('Original smoke-only ledger required')
    elif output.exists():raise IntegrityError('Existing run: never reset/replay the ledger')
    j=Journal(output,91,2)
    if continuing:check_topup_continuation(j,3 if args.payg_smoke_only else 2 if args.after_owner_key_update else 1)
    client=HttpClient('mistral',os.environ['MISTRAL_API_KEY'],ca_file='/etc/ssl/cert.pem')
    smoke,rid,directory=capture(j,client,'mistral','SMOKE_AFTER_OWNER_PAYG' if args.payg_smoke_only else 'SMOKE_AFTER_OWNER_KEY_UPDATE' if args.after_owner_key_update else 'SMOKE_AFTER_OWNER_TOPUP' if args.after_owner_topup else 'SMOKE',[{'role':'system','content':'Return only a JSON object.'},{'role':'user','content':'Return exactly {"ok":true}.'}])
    ok=smoke['status']=='complete' and smoke.get('parsed_output')=={'ok':True} and isinstance(smoke.get('assistant_content_bytes'),bytes)
    save_json(directory/'step.json',{'kind':'compatibility_smoke_not_scientific_case','compatible':ok,'request_id':rid});j.processed(rid)
    save_json(PRIVATE/('smoke-after-payg.json' if args.payg_smoke_only else 'smoke-after-key-update.json' if args.after_owner_key_update else 'smoke-after-topup.json' if args.after_owner_topup else 'smoke.json'),{'request_id':rid,'status':smoke['status'],'compatible':ok,'classification':'PASS' if ok else classify(smoke,(directory/'response.bin').read_bytes())})
    print(json.dumps({'smoke':'PASS' if ok else 'FAIL','attempts_consumed':4 if args.payg_smoke_only else 3 if args.after_owner_key_update else 2 if args.after_owner_topup else 1}),flush=True)
    if not ok or args.payg_smoke_only:return
    results=[]
    worlds=json.loads((ROOT/'research/p8/scenarios.json').read_text())
    for w in worlds:
        try:r=run_episode(w,client,j,'mistral',name=w['id'])
        except IntegrityError:
            path=output/w['id']/'result.json'
            r=json.loads(path.read_text()) if path.exists() else {'name':w['id'],'status':'integrity_failure'}
            results.append(r);save_json(PRIVATE/'results.json',{'results':results,'stopped':'integrity_or_unknown_completion'});return
        results.append(r);save_json(PRIVATE/'results.json',{'results':results,'stopped':None})
        print(json.dumps({'world':w['id'],'status':r['status'],'responses':r.get('model_responses'),'action':(r.get('decision') or {}).get('action'),'correct':r.get('evaluation',{}).get('independent_outcome_correct')}),flush=True)
        if r.get('last_request_id'):
            cap=output/r['last_request_id'];c=json.loads((cap/'capture.json').read_text())
            if c.get('http_status') in (401,402,403,429):
                save_json(PRIVATE/'results.json',{'results':results,'stopped':classify(c,(cap/'response.bin').read_bytes())});return
    save_json(PRIVATE/'results.json',{'results':results,'stopped':None,'smoke_included_in_cap':True,'total_attempt_cap':91,'spending_ceiling_usd':2})


if __name__=='__main__':main()
