"""Owner-authorised13-case continuation; same journal, no new smoke or retries."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

from tools.mistral_pilot.__main__ import PRIVATE, ROOT, classify
from tools.p4_world.world import canonical
from tools.p5_interactive.experiment import run_episode
from tools.p5_interactive.operational_check import replay_trace
from tools.p5_interactive.operational_reference import evaluate_outcome
from tools.p5_interactive.providers import (
    HttpClient,
    IntegrityError,
    Journal,
    save_json,
)


def extend_existing_budget(root: Path) -> Journal:
    if not (root/'calls.sqlite').is_file():raise IntegrityError('Original journal required')
    j=Journal(root,91,2)
    with j.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        rows=db.execute('SELECT id,episode,route,status,reservation FROM calls').fetchall()
        if db.execute('SELECT stop FROM settings WHERE id=1').fetchone()[0] or len(rows)!=4 or any(r[2:4]!=('mistral','processed') for r in rows):
            raise IntegrityError('Exactly four processed original smokes and no STOP required')
        expected={'SMOKE':429,'SMOKE_AFTER_OWNER_TOPUP':429,'SMOKE_AFTER_OWNER_KEY_UPDATE':429,'SMOKE_AFTER_OWNER_PAYG':200}
        if {r[1] for r in rows}!=set(expected):raise IntegrityError('Unexpected prior episodes')
        for rid,name,*_ in rows:
            c=json.loads((root/rid/'capture.json').read_text())
            if c['http_status']!=expected[name] or c.get('unknown_completion'):raise IntegrityError('Smoke evidence differs')
            if expected[name]==200 and (c['model']!='mistral-small-2603' or c['parsed_output']!={'ok':True}):raise IntegrityError('Successful smoke required')
        save_json(root.parent/'scientific-budget-amendment.json',{'old_cap':91,'new_cap':95,'scientific_additional_cap':91,'ceiling_usd':2,'prior_calls':rows,'reason':'explicit owner authorization; no accounting reset'})
        db.execute('UPDATE settings SET max_requests=95 WHERE id=1 AND max_requests=91 AND ceiling=2')
    return Journal(root,95,2)


class PacedClient(HttpClient):
    """The existing client, with durable-history-based pacing and separate timing."""
    def __init__(self, secret: str, journal: Journal, *, minimum_gap_s: float = 15.0):
        if not math.isfinite(minimum_gap_s) or minimum_gap_s<15:
            raise ValueError('Prospective Mistral gap must be at least15seconds')
        self.minimum_gap_s=minimum_gap_s
        super().__init__('mistral',secret,ca_file='/etc/ssl/cert.pem')
        self.journal=journal
        self.wait_s=0.0

    def _pace(self) -> None:
        latest=0.0
        for p in self.journal.root.glob('P5-*/capture.json'):
            c=json.loads(p.read_text())
            latest=max(latest,dt.datetime.fromisoformat(c['finished_at']).timestamp())
        start=time.monotonic()
        while (remaining:=latest+self.minimum_gap_s-time.time())>0:time.sleep(min(remaining,30))
        self.wait_s=time.monotonic()-start

    def send(self, body: bytes, request_id: str, directory: Path) -> tuple[str,int|None]:
        start=time.monotonic();result=super().send(body,request_id,directory)
        elapsed=time.monotonic()-start
        save_json(directory/'timing.json',{'scheduler_wait_s':self.wait_s,'api_transport_elapsed_s':elapsed-self.wait_s,
                  'total_send_elapsed_s':elapsed,'minimum_gap_after_previous_capture_s':self.minimum_gap_s,'api_latency_definition':'client transport elapsed excluding scheduler; includes TLS and process startup'})
        return result


def verify_episode(world: dict[str,Any], result: dict[str,Any], j: Journal) -> None:
    directory=j.root/world['id'];trace=(directory/'trace.jsonl').read_bytes()
    if result.get('replay'):
        replay=result['replay'];decision=result['decision']
        if replay_trace(world,trace)!=replay:raise IntegrityError('Replay differs')
        if replay['I2']['proposal_sha256']!=replay['I3']['proposal_sha256']:raise IntegrityError('Proposal identity differs')
        if hashlib.sha256(canonical(decision).encode()).hexdigest()!=replay['I2']['proposal_sha256']:raise IntegrityError('Proposal differs')
        if evaluate_outcome(world,trace,decision,replay,condition={'tools':True,'user_answers':True})!=result['evaluation']:raise IntegrityError('Independent score differs')
    with j.connect() as db:
        rows=db.execute('SELECT id,status FROM calls WHERE episode=?',(world['id'],)).fetchall()
    for rid,status in rows:
        p=j.root/rid;c=json.loads((p/'capture.json').read_text())
        if status!='processed' or not (p/'step.json').exists():raise IntegrityError('Unfinished workflow')
        for name in ['request','response']:
            if hashlib.sha256((p/f'{name}.bin').read_bytes()).hexdigest()!=c[f'{name}_sha256']:raise IntegrityError('Capture bytes differ')
        if c['status']=='complete' and (c['model']!='mistral-small-2603' or not isinstance(c.get('usage'),dict)):raise IntegrityError('Identity/usage missing')


def record_progress(root: Path, payload: dict[str,Any], *, terminal: bool) -> None:
    """Append one immutable snapshot per episode; final aggregate is written once."""
    save_json(root/f"scientific-progress-{len(payload['results']):02}.json",payload)
    if terminal:save_json(root/'scientific-results.json',payload)


def release_repaired_stop(j: Journal) -> None:
    """Only the explicitly approved persistence STOP may be cleared; retain receipt."""
    receipt=j.root.parent/'owner-authorised-stop-release.json'
    with j.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        stop=db.execute('SELECT stop FROM settings WHERE id=1').fetchone()[0]
        rows=db.execute('SELECT id,episode,status,reservation FROM calls ORDER BY rowid').fetchall()
        if stop is None and receipt.exists():return  # local driver restart, never repeats a completed case
        if stop!='aggregate_persistence_failure_no_automatic_continuation':raise IntegrityError('Not the authorised repaired STOP')
        if len(rows)!=10 or any(r[2]!='processed' for r in rows):raise IntegrityError('Ten processed prior attempts required')
        if sum(r[3] for r in rows)>2:raise IntegrityError('Prior budget exceeded')
        save_json(receipt,{'previous_stop':stop,'reason':'explicit researcher authorization to continue P8-03 through13 after offline persistence fix','prior_calls':rows,'limits_unchanged':[95,2],'cleared_at':dt.datetime.now(dt.UTC).isoformat()})
        db.execute('UPDATE settings SET stop=NULL WHERE id=1 AND stop=?',(stop,))


def continue_remaining() -> None:
    freeze=json.loads((ROOT/'evidence/mistral-pilot/continuation-pre-inference-freeze.json').read_text())
    for n,h in freeze['files'].items():
        if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h:raise IntegrityError('Continuation source differs')
    with (PRIVATE/'scientific-collection.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        j=Journal(PRIVATE/'run',95,2)
        worlds=json.loads((ROOT/'research/p8/scenarios.json').read_text())
        results=[]
        # Verify original raw bytes/status before releasing the particular STOP.
        with j.connect() as db:rows=db.execute('SELECT id,status FROM calls').fetchall()
        for rid,status in rows:
            d=j.root/rid;c=json.loads((d/'capture.json').read_text())
            if status!='processed' or c.get('unknown_completion') or not (d/'step.json').exists():raise IntegrityError('Unfinished/unknown attempt')
            for name in ['request','response']:
                if hashlib.sha256((d/f'{name}.bin').read_bytes()).hexdigest()!=c[f'{name}_sha256']:raise IntegrityError('Original bytes differ')
        for w in worlds[:2]:
            r=json.loads((j.root/w['id']/'result.json').read_text());verify_episode(w,r,j);results.append(r)
        release_repaired_stop(j)
        client=PacedClient(os.environ['MISTRAL_API_KEY'],j);stopped=None
        for w in worlds[2:]:
            existing=j.root/w['id']/'result.json'
            if existing.exists():
                r=json.loads(existing.read_text());verify_episode(w,r,j)
            else:
                r=run_episode(w,client,j,'mistral',name=w['id']);verify_episode(w,r,j)
            results.append(r)
            if r.get('last_request_id'):
                d=j.root/r['last_request_id'];c=json.loads((d/'capture.json').read_text())
                if c.get('http_status') in (401,402,403,429) or c.get('unknown_completion'):stopped=classify(c,(d/'response.bin').read_bytes())
            if r['status'] in ('incomplete_budget','collection_paused'):stopped=r['status']
            payload={'results':results,'stopped':stopped,'total_cap':95,'scientific_cap':91,'ceiling_usd':2,'prior_two_episodes_not_repeated':True}
            progress=PRIVATE/f"scientific-resume-progress-{len(results):02}.json"
            if not progress.exists():save_json(progress,payload)
            print(json.dumps({'world':w['id'],'status':r['status'],'responses':r.get('model_responses'),'action':(r.get('decision') or {}).get('action'),'correct':r.get('evaluation',{}).get('independent_outcome_correct'),'stopped':stopped}),flush=True)
            if stopped:j.stop(stopped);break
        save_json(PRIVATE/'scientific-results-completed.json',{'results':results,'stopped':stopped,'total_cap':95,'scientific_cap':91,'ceiling_usd':2,'prior_two_episodes_not_repeated':True})


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',action='store_true');p.add_argument('--continue-remaining',action='store_true');args=p.parse_args()
    if not args.live:p.error('Explicit --live required')
    if args.continue_remaining:
        continue_remaining();return
    freeze=json.loads((ROOT/'evidence/mistral-pilot/scientific-pre-inference-freeze.json').read_text())
    for n,h in freeze['files'].items():
        if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h:raise IntegrityError('Frozen source differs')
    if (PRIVATE/'results.json').exists():raise IntegrityError('Existing scientific results; no automatic replay')
    with (PRIVATE/'scientific-collection.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        j=extend_existing_budget(PRIVATE/'run');client=PacedClient(os.environ['MISTRAL_API_KEY'],j)
        results=[];stopped=None
        for w in json.loads((ROOT/'research/p8/scenarios.json').read_text()):
            try:
                r=run_episode(w,client,j,'mistral',name=w['id'])
                verify_episode(w,r,j)
            except Exception as exc:
                stopped='evidence_or_integrity_failure:'+type(exc).__name__
                j.stop(stopped)
                existing=j.root/w['id']/'result.json'
                if existing.exists():results.append(json.loads(existing.read_text()))
                save_json(PRIVATE/'scientific-exception.json',{'results':results,'stopped':stopped});raise
            results.append(r)
            if r.get('last_request_id'):
                d=j.root/r['last_request_id'];c=json.loads((d/'capture.json').read_text())
                if c.get('http_status') in (401,402,403,429) or c.get('unknown_completion'):stopped=classify(c,(d/'response.bin').read_bytes())
            if r['status'] in ('incomplete_budget','collection_paused'):stopped=r['status']
            payload={'results':results,'stopped':stopped,'technical_first_episode_verified':True,'total_cap':95,'scientific_cap':91,'ceiling_usd':2}
            try:record_progress(PRIVATE,payload,terminal=bool(stopped) or len(results)==13)
            except Exception:
                j.stop('aggregate_persistence_failure_no_automatic_continuation')
                raise

            print(json.dumps({'world':w['id'],'status':r['status'],'responses':r.get('model_responses'),'action':(r.get('decision') or {}).get('action'),'correct':r.get('evaluation',{}).get('independent_outcome_correct'),'stopped':stopped}),flush=True)
            if stopped:j.stop(stopped);break


if __name__=='__main__':main()
